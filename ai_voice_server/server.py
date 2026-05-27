import base64
import json
import os
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from openai import OpenAI

app = FastAPI(title="Odoo AI Voice Proxy Gateway", version="2.0")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MOCK_MODE = os.environ.get("MOCK_MODE", "false").lower() == "true" or not OPENAI_API_KEY

if not MOCK_MODE:
    OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)
else:
    OPENAI_CLIENT = None

# UUIDs of active subscribed Odoo databases
ACTIVE_SUBSCRIBERS: list[str] = [
    "odoo-uuid-standard-customer-12345",
    "odoo-uuid-court-custom-67890",
]


class VoiceRequest(BaseModel):
    db_uuid: str = Field(..., description="المعرف الفريد لقاعدة بيانات أودو للعميل")
    res_model: str = Field(..., description="اسم الموديول الحالي في أودو")
    res_id: Optional[int] = Field(None, description="معرف السجل الحالي في حال التعديل أو القراءة")
    model_schema: Dict[str, Any] = Field(..., description="بنية الحقول الحالية للشاشة المفتوحة في أودو")
    audio_base64: str = Field(..., description="الملف الصوتي مسجل ومحمول بصيغة Base64")
    # Optional: allow passing text directly in mock/test mode
    mock_speech_text: Optional[str] = Field(None, description="نص بديل عن الصوت (للاختبار فقط)")


class OdooActionResponse(BaseModel):
    intent: str = Field(
        ...,
        description="يجب أن يكون: 'create' أو 'update' أو 'navigate' أو 'report' أو 'extract'",
    )
    extracted_data: Dict[str, Any] = Field(
        ...,
        description="قاموس يحتوي أسماء حقول أودو البرمجية وقيمها المستخرجة",
    )
    report_instruction: Optional[str] = Field(
        None,
        description="في حال كان intent هو report، هنا توضع صياغة التقرير القانونية الرسمية",
    )
    feedback_message: str = Field(
        ...,
        description="رسالة نصية موجهة للمستخدم تشرح ما تم فهمه وتنفيذه باللغة العربية",
    )


def _mock_ai_response(speech_text: str, res_model: str, res_id: Optional[int]) -> OdooActionResponse:
    """Generate a simulated AI response based on keywords in the speech text."""
    text = speech_text.strip()

    # --- Scenario 1: Report / Legal formatting ---
    if any(kw in text for kw in ["تقرير", "صياغة", "ملخص", "تلخيص", "report"]):
        return OdooActionResponse(
            intent="report",
            extracted_data={},
            report_instruction=(
                f"بناءً على الصلاحيات الممنوحة، جرى الاطلاع على مجريات السجل رقم {res_id or 'N/A'} "
                f"في موديول ({res_model}). وحيث تبينت الحاجة للتدقيق، أصدرت الأمانة العامة "
                "أمراً برفع الجلسة وتأجيلها، صياغةً رسمية معتمدة."
            ),
            feedback_message=f"✅ تمت إعادة صياغة التقرير للسجل رقم {res_id or 'N/A'} بالأسلوب القانوني الرسمي.",
        )

    # --- Scenario 2: Update existing record ---
    if any(kw in text for kw in ["عدّل", "عدل", "غير", "بدّل", "update", "تعديل"]) and res_id:
        # Parse simple "field = value" patterns for demo
        extracted: Dict[str, Any] = {}
        if "اسم" in text or "name" in text:
            parts = text.split()
            # Take last two words as name candidate
            extracted["name"] = " ".join(parts[-2:]) if len(parts) >= 2 else "قيمة مستخرجة"
        if "تاريخ" in text or "date" in text:
            extracted["date"] = "2026-05-27"
        if not extracted:
            extracted["name"] = "قيمة مُعدَّلة تجريبية"
        return OdooActionResponse(
            intent="update",
            extracted_data=extracted,
            report_instruction=None,
            feedback_message=f"✅ تم تعديل بيانات السجل رقم {res_id} في ({res_model}) بنجاح.",
        )

    # --- Scenario 3: Create new record ---
    if any(kw in text for kw in ["أنشئ", "انشئ", "جديد", "سجل", "create", "أضف", "اضف"]):
        extracted = {}
        if res_model == "sale.order":
            extracted = {"partner_id": "شركة الاختبار", "order_line": [{"product_id": "منتج تجريبي", "product_uom_qty": 1}]}
        elif "court" in res_model:
            extracted = {"session_date": "2026-06-01", "judge_notes": "ملاحظة تجريبية من الذكاء الاصطناعي"}
        else:
            extracted = {"name": "سجل جديد من الذكاء الاصطناعي"}
        return OdooActionResponse(
            intent="create",
            extracted_data=extracted,
            report_instruction=None,
            feedback_message=f"✅ تم فهم طلب الإنشاء في ({res_model}). جارٍ فتح نموذج جديد.",
        )

    # --- Default: unknown intent ---
    return OdooActionResponse(
        intent="extract",
        extracted_data={"raw_text": text},
        report_instruction=None,
        feedback_message=f"🔍 تم استقبال الطلب: \"{text}\" — لم يتم التعرف على نية محددة.",
    )


def _build_system_prompt(res_model: str, model_schema: Dict, res_id: Optional[int]) -> str:
    return f"""أنت محرك ذكاء اصطناعي متكامل مدمج داخل نظام Odoo ERP الإداري.
مهمتك هي الاستماع لطلب المستخدم وتحديد نيته (intent) واستخراج البيانات المطابقة لحقول النظام الحالية.

بنية الحقول الحالية للموديول المفتوح ({res_model}):
{json.dumps(model_schema, ensure_ascii=False)}

{'معرف السجل الحالي (res_id): ' + str(res_id) if res_id else 'لا يوجد سجل مفتوح، هذه شاشة إنشاء جديدة'}

قواعد حاسمة:
1. إذا طلب المستخدم إنشاء شيء جديد، اجعل intent يساوي 'create'.
2. إذا طلب التعديل على السجل المفتوح حالياً، اجعل intent يساوي 'update'.
3. إذا طلب مراجعة أو صياغة تقرير، اجعل intent يساوي 'report' وضع الصياغة في report_instruction.
4. إذا طلب الانتقال لسجل معين، اجعل intent يساوي 'navigate'.
5. إذا كان نوع الحقل 'date'، يجب أن تكون الصيغة (YYYY-MM-DD).
6. لا تخترع حقولاً غير موجودة في بنية الحقول المعطاة.
"""


@app.post("/v1/process-voice", response_model=OdooActionResponse)
async def process_voice(request: VoiceRequest):
    # 1. Verify subscription
    if request.db_uuid not in ACTIVE_SUBSCRIBERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="اشتراكك منتهي أو غير فعال في الخدمة الصوتية لأودو. يرجى التجديد.",
        )

    try:
        # 2. Determine speech text
        if request.mock_speech_text:
            # Text provided directly (test/mock mode)
            user_speech_text = request.mock_speech_text
        elif MOCK_MODE:
            # Mock mode without real audio — decode to get placeholder text
            raw = base64.b64decode(request.audio_base64 + "==").decode("utf-8", errors="replace")
            user_speech_text = raw.strip() or "طلب تجريبي"
        else:
            # Real mode: decode audio and call Whisper
            audio_bytes = base64.b64decode(request.audio_base64)
            temp_file_path = f"/tmp/{request.db_uuid}.wav"
            with open(temp_file_path, "wb") as f:
                f.write(audio_bytes)
            with open(temp_file_path, "rb") as audio_file:
                transcription = OPENAI_CLIENT.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ar",
                )
            user_speech_text = transcription.text

        # 3. Process with AI (mock or real)
        if MOCK_MODE:
            result = _mock_ai_response(user_speech_text, request.res_model, request.res_id)
        else:
            system_prompt = _build_system_prompt(
                request.res_model, request.model_schema, request.res_id
            )
            completion = OPENAI_CLIENT.beta.chat.completions.parse(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"نص كلام المستخدم الصوتي هو: {user_speech_text}"},
                ],
                response_format=OdooActionResponse,
            )
            result = completion.choices[0].message.parsed

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"خطأ في معالجة السيرفر للذكاء الاصطناعي: {str(e)}",
        )


@app.get("/health")
async def health_check():
    mode = "mock" if MOCK_MODE else "production"
    return {
        "status": "ok",
        "service": "Odoo AI Voice Proxy Gateway",
        "mode": mode,
        "active_subscribers": len(ACTIVE_SUBSCRIBERS),
    }
