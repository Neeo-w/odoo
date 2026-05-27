import base64
import json
import os
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

app = FastAPI(title="Odoo AI Voice Proxy Gateway", version="2.0")

# ─── Provider Configuration ──────────────────────────────────────────────────
PROVIDER       = os.environ.get("AI_PROVIDER", "groq").lower()   # groq | openai
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MOCK_MODE      = os.environ.get("MOCK_MODE", "false").lower() == "true"

if not MOCK_MODE:
    if PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY غير موجود. قم بتعيين متغير البيئة GROQ_API_KEY")
        from groq import Groq
        AI_CLIENT = Groq(api_key=GROQ_API_KEY)
        STT_MODEL  = "whisper-large-v3"
        CHAT_MODEL = "llama-3.3-70b-versatile"
    else:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY غير موجود")
        from openai import OpenAI
        AI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)
        STT_MODEL  = "whisper-1"
        CHAT_MODEL = "gpt-4o"
else:
    AI_CLIENT = None
    STT_MODEL  = ""
    CHAT_MODEL = ""

# ─── Active subscribers ──────────────────────────────────────────────────────
ACTIVE_SUBSCRIBERS: list[str] = [
    "odoo-uuid-standard-customer-12345",
    "odoo-uuid-court-custom-67890",
]

# ─── Pydantic models ─────────────────────────────────────────────────────────

class VoiceRequest(BaseModel):
    db_uuid: str = Field(..., description="المعرف الفريد لقاعدة بيانات أودو")
    res_model: str = Field(..., description="اسم الموديول الحالي في أودو")
    res_id: Optional[int] = Field(None, description="معرف السجل المفتوح")
    model_schema: Dict[str, Any] = Field(..., description="بنية حقول الشاشة المفتوحة")
    audio_base64: str = Field(..., description="الملف الصوتي بصيغة Base64")
    mock_speech_text: Optional[str] = Field(None, description="نص بديل للاختبار (بدون صوت)")


class OdooActionResponse(BaseModel):
    intent: str = Field(..., description="create | update | navigate | report | extract")
    extracted_data: Dict[str, Any] = Field(..., description="قاموس حقول أودو وقيمها")
    report_instruction: Optional[str] = Field(None, description="صياغة التقرير الرسمي")
    feedback_message: str = Field(..., description="رسالة للمستخدم بالعربية")


# ─── JSON schema for structured output prompt ─────────────────────────────────
_RESPONSE_SCHEMA = """
{
  "intent": "<create|update|navigate|report|extract>",
  "extracted_data": { "<field_name>": "<value>", ... },
  "report_instruction": "<نص التقرير الرسمي أو null>",
  "feedback_message": "<رسالة عربية للمستخدم>"
}
"""

def _build_system_prompt(res_model: str, model_schema: Dict, res_id: Optional[int]) -> str:
    return f"""أنت محرك ذكاء اصطناعي متكامل مدمج داخل نظام Odoo ERP.
مهمتك: استمع لطلب المستخدم، حدد نيته، واستخرج البيانات المطابقة لحقول النظام.

الموديول الحالي: {res_model}
بنية الحقول المتاحة:
{json.dumps(model_schema, ensure_ascii=False, indent=2)}

السجل المفتوح: {f"res_id={res_id}" if res_id else "لا يوجد سجل — شاشة إنشاء جديدة"}

قواعد حاسمة:
1. intent='create'   → المستخدم يريد إنشاء سجل جديد
2. intent='update'   → المستخدم يريد تعديل السجل المفتوح (res_id موجود)
3. intent='report'   → مراجعة/تلخيص/تقرير رسمي — ضع الصياغة في report_instruction
4. intent='navigate' → التنقل لسجل معين
5. حقول 'date' يجب أن تكون بصيغة YYYY-MM-DD
6. لا تخترع حقولاً غير موجودة في بنية الحقول

أجب فقط بـ JSON صحيح يتبع هذا الهيكل بالضبط:
{_RESPONSE_SCHEMA}
"""


def _call_ai(speech_text: str, res_model: str, model_schema: Dict, res_id: Optional[int]) -> OdooActionResponse:
    """Call Groq or OpenAI and parse structured response."""
    system_prompt = _build_system_prompt(res_model, model_schema, res_id)

    if PROVIDER == "groq":
        resp = AI_CLIENT.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"كلام المستخدم: {speech_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw_json = resp.choices[0].message.content
        data = json.loads(raw_json)
    else:
        # OpenAI structured output via Pydantic
        resp = AI_CLIENT.beta.chat.completions.parse(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"كلام المستخدم: {speech_text}"},
            ],
            response_format=OdooActionResponse,
            temperature=0.1,
        )
        return resp.choices[0].message.parsed

    return OdooActionResponse(**data)


def _transcribe_audio(audio_b64: str, db_uuid: str) -> str:
    """Decode base64 audio and transcribe via Whisper (Groq or OpenAI)."""
    audio_bytes = base64.b64decode(audio_b64)
    tmp_path = f"/tmp/ai_voice_{db_uuid}.webm"
    with open(tmp_path, "wb") as f:
        f.write(audio_bytes)
    with open(tmp_path, "rb") as f:
        transcription = AI_CLIENT.audio.transcriptions.create(
            model=STT_MODEL,
            file=f,
            language="ar",
        )
    return transcription.text


# ─── Mock fallback ────────────────────────────────────────────────────────────
def _mock_ai_response(text: str, res_model: str, res_id: Optional[int]) -> OdooActionResponse:
    if any(k in text for k in ["تقرير", "صياغة", "ملخص", "تلخيص"]):
        return OdooActionResponse(
            intent="report",
            extracted_data={},
            report_instruction=(
                f"بناءً على الصلاحيات الممنوحة، جرى الاطلاع على مجريات السجل رقم "
                f"{res_id or 'N/A'} في موديول ({res_model})، وأصدرت الأمانة العامة "
                "أمراً بالتأجيل صياغةً رسمية معتمدة."
            ),
            feedback_message=f"✅ تمت إعادة صياغة التقرير للسجل {res_id or 'N/A'} بالأسلوب القانوني الرسمي.",
        )
    if any(k in text for k in ["عدّل", "عدل", "غيّر", "بدّل", "تعديل"]) and res_id:
        words = text.split()
        return OdooActionResponse(
            intent="update",
            extracted_data={"name": " ".join(words[-2:]) if len(words) >= 2 else "قيمة تجريبية"},
            report_instruction=None,
            feedback_message=f"✅ تم تعديل السجل رقم {res_id} في ({res_model}).",
        )
    extracted: Dict[str, Any] = {}
    if res_model == "sale.order":
        extracted = {"partner_id": "شركة الاختبار", "order_line": [{"product_id": "منتج تجريبي", "product_uom_qty": 1}]}
    elif "court" in res_model:
        extracted = {"session_date": "2026-06-01", "judge_notes": "ملاحظة تجريبية"}
    else:
        extracted = {"name": "سجل جديد من الذكاء الاصطناعي"}
    return OdooActionResponse(
        intent="create",
        extracted_data=extracted,
        report_instruction=None,
        feedback_message=f"✅ تم فهم طلب الإنشاء في ({res_model}). جارٍ فتح نموذج جديد.",
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/v1/process-voice", response_model=OdooActionResponse)
async def process_voice(request: VoiceRequest):
    if request.db_uuid not in ACTIVE_SUBSCRIBERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="اشتراكك منتهي أو غير فعال في الخدمة الصوتية لأودو. يرجى التجديد.",
        )
    try:
        # Determine speech text
        if request.mock_speech_text:
            speech_text = request.mock_speech_text
        elif MOCK_MODE:
            raw = base64.b64decode(request.audio_base64 + "==").decode("utf-8", errors="replace")
            speech_text = raw.strip() or "طلب تجريبي"
        else:
            speech_text = _transcribe_audio(request.audio_base64, request.db_uuid)

        # Generate AI response
        if MOCK_MODE:
            return _mock_ai_response(speech_text, request.res_model, request.res_id)
        else:
            return _call_ai(speech_text, request.res_model, request.model_schema, request.res_id)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"خطأ في معالجة السيرفر: {str(e)}",
        )


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "Odoo AI Voice Proxy Gateway",
        "provider": PROVIDER if not MOCK_MODE else "mock",
        "stt_model": STT_MODEL or "mock",
        "chat_model": CHAT_MODEL or "mock",
        "active_subscribers": len(ACTIVE_SUBSCRIBERS),
    }
