import base64
import json
import os
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from openai import OpenAI

app = FastAPI(title="Odoo AI Voice Proxy Gateway", version="2.0")

OPENAI_CLIENT = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY"))

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


@app.post("/v1/process-voice", response_model=OdooActionResponse)
async def process_voice(request: VoiceRequest):
    # 1. Verify subscription
    if request.db_uuid not in ACTIVE_SUBSCRIBERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="اشتراكك منتهي أو غير فعال في الخدمة الصوتية لأودو. يرجى التجديد.",
        )

    try:
        # 2. Decode audio and save as temp file
        audio_bytes = base64.b64decode(request.audio_base64)
        temp_file_path = f"/tmp/{request.db_uuid}.wav"
        with open(temp_file_path, "wb") as f:
            f.write(audio_bytes)

        # 3. Transcribe audio via Whisper
        with open(temp_file_path, "rb") as audio_file:
            transcription = OPENAI_CLIENT.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ar",
            )

        user_speech_text = transcription.text

        # 4. Build prompt with Odoo model schema
        system_prompt = f"""أنت محرك ذكاء اصطناعي متكامل مدمج داخل نظام Odoo ERP الإداري.
مهمتك هي الاستماع لطلب المستخدم وتحديد نيته (intent) واستخراج البيانات المطابقة لحقول النظام الحالية.

بنية الحقول الحالية للموديول المفتوح ({request.res_model}):
{json.dumps(request.model_schema, ensure_ascii=False)}

{'معرف السجل الحالي (res_id): ' + str(request.res_id) if request.res_id else 'لا يوجد سجل مفتوح، هذه شاشة إنشاء جديدة'}

قواعد حاسمة:
1. إذا طلب المستخدم إنشاء شيء جديد، اجعل intent يساوي 'create'.
2. إذا طلب التعديل على السجل المفتوح حالياً، اجعل intent يساوي 'update'.
3. إذا طلب مراجعة، تلخيص، أو صياغة تقرير بناءً على السجل المفتوح، اجعل intent يساوي 'report' وضع الصياغة البليغة الرسمية في حقل report_instruction.
4. إذا طلب الانتقال إلى صفحة أو سجل معين، اجعل intent يساوي 'navigate'.
5. طابق قيم النص مع أسماء الحقول (Keys) المرسلة إليك. إذا كان نوع الحقل 'date' يجب أن تكون الصيغة (YYYY-MM-DD).
6. لا تخترع حقولاً غير موجودة في بنية الحقول المعطاة.
"""

        # 5. Call GPT-4o with structured output enforcement
        completion = OPENAI_CLIENT.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"نص كلام المستخدم الصوتي هو: {user_speech_text}"},
            ],
            response_format=OdooActionResponse,
        )

        # 6. Return structured result to Odoo client
        return completion.choices[0].message.parsed

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"خطأ في معالجة السيرفر للذكاء الاصطناعي: {str(e)}",
        )


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Odoo AI Voice Proxy Gateway"}
