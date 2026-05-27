"""
اختبارات شاملة لـ Odoo AI Voice Proxy Gateway
يغطي السيناريوهات الثلاثة الواردة في الملف + حالات الخطأ
"""
import base64
import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"

# ─── helpers ────────────────────────────────────────────────────────────────

def post(endpoint: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        return e.code, body

def text_to_b64(text: str) -> str:
    """Encode text as base64 to simulate audio payload in mock mode."""
    return base64.b64encode(text.encode()).decode()

def check(condition: bool, msg: str):
    icon = "✅" if condition else "❌"
    print(f"  {icon} {msg}")
    if not condition:
        sys.exit(1)

def section(title: str):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")

# ─── tests ──────────────────────────────────────────────────────────────────

def test_health():
    section("1. Health Check")
    import urllib.request
    with urllib.request.urlopen(f"{BASE_URL}/health") as r:
        data = json.loads(r.read())
    check(data["status"] == "ok", "status = ok")
    check(data["mode"] == "mock", "وضع المحاكاة مفعّل")
    check(data["active_subscribers"] == 2, "عدد المشتركين = 2")
    print(f"  ℹ️  mode={data['mode']}, subscribers={data['active_subscribers']}")


def test_unauthorized_uuid():
    section("2. رفض UUID غير مسجّل (403)")
    code, body = post("/v1/process-voice", {
        "db_uuid": "odoo-uuid-UNKNOWN-9999",
        "res_model": "sale.order",
        "res_id": None,
        "model_schema": {},
        "audio_base64": text_to_b64("أنشئ طلب"),
        "mock_speech_text": "أنشئ طلب جديد",
    })
    check(code == 403, f"HTTP 403 — حصلنا على {code}")
    check("detail" in body, "رسالة الخطأ موجودة")
    print(f"  ℹ️  detail: {body['detail']}")


def test_scenario_1_report():
    section("3. السيناريو 1 — موديول القضاء: صياغة تقرير قانوني")
    code, body = post("/v1/process-voice", {
        "db_uuid": "odoo-uuid-court-custom-67890",
        "res_model": "court.session",
        "res_id": 105,
        "model_schema": {
            "session_date": {"type": "date", "string": "تاريخ الجلسة"},
            "judge_notes": {"type": "text", "string": "ملاحظات القاضي"},
            "final_decision": {"type": "text", "string": "القرار النهائي والمحضر الرسمي"},
        },
        "audio_base64": text_to_b64("محاكاة صوتية"),
        "mock_speech_text": "أعد صياغة تقرير هذه الجلسة بأسلوب قانوني رسمي واكتب أنه تقرر تأجيل الجلسة لثلاثة أيام",
    })
    check(code == 200, f"HTTP 200 — حصلنا على {code}")
    check(body.get("intent") == "report", f"intent=report — حصلنا على '{body.get('intent')}'")
    check(body.get("report_instruction") is not None, "report_instruction موجود")
    check(len(body.get("feedback_message", "")) > 0, "feedback_message غير فارغة")
    print(f"  ℹ️  feedback: {body['feedback_message']}")
    print(f"  ℹ️  report_instruction: {body['report_instruction'][:80]}...")


def test_scenario_2_update():
    section("4. السيناريو 2 — موديول القضاء: تعديل بيانات سجل مفتوح")
    code, body = post("/v1/process-voice", {
        "db_uuid": "odoo-uuid-court-custom-67890",
        "res_model": "court.session",
        "res_id": 105,
        "model_schema": {
            "witness_name": {"type": "char", "string": "اسم الشاهد"},
            "case_status": {"type": "selection", "string": "حالة القضية",
                            "selection": [["open", "مفتوحة"], ["closed", "مغلقة"]]},
        },
        "audio_base64": text_to_b64("محاكاة صوتية"),
        "mock_speech_text": "عدّل اسم الشاهد في هذه الجلسة واجعله فهد بن أحمد",
    })
    check(code == 200, f"HTTP 200 — حصلنا على {code}")
    check(body.get("intent") == "update", f"intent=update — حصلنا على '{body.get('intent')}'")
    check(body.get("report_instruction") is None, "report_instruction = null (صحيح)")
    check(isinstance(body.get("extracted_data"), dict), "extracted_data هو dict")
    check(len(body["extracted_data"]) > 0, "extracted_data غير فارغ")
    print(f"  ℹ️  extracted_data: {body['extracted_data']}")
    print(f"  ℹ️  feedback: {body['feedback_message']}")


def test_scenario_3_create():
    section("5. السيناريو 3 — المبيعات: إنشاء أمر بيع جديد")
    code, body = post("/v1/process-voice", {
        "db_uuid": "odoo-uuid-standard-customer-12345",
        "res_model": "sale.order",
        "res_id": None,
        "model_schema": {
            "partner_id": {"type": "many2one", "string": "العميل"},
            "order_line": {"type": "one2many", "string": "خطوط المنتجات"},
        },
        "audio_base64": text_to_b64("محاكاة صوتية"),
        "mock_speech_text": "سجّل طلب جديد لشركة المراعي، المنتج طاولة مكتبية والكمية 10 حبات",
    })
    check(code == 200, f"HTTP 200 — حصلنا على {code}")
    check(body.get("intent") == "create", f"intent=create — حصلنا على '{body.get('intent')}'")
    check(body.get("report_instruction") is None, "report_instruction = null (صحيح)")
    data = body.get("extracted_data", {})
    check("partner_id" in data or "order_line" in data, "extracted_data يحتوي حقول sale.order")
    print(f"  ℹ️  extracted_data: {json.dumps(data, ensure_ascii=False)}")
    print(f"  ℹ️  feedback: {body['feedback_message']}")


def test_missing_fields():
    section("6. طلب ناقص الحقول (422 Validation Error)")
    code, body = post("/v1/process-voice", {
        "db_uuid": "odoo-uuid-standard-customer-12345",
        # missing: res_model, model_schema, audio_base64
    })
    check(code == 422, f"HTTP 422 — حصلنا على {code}")
    print(f"  ℹ️  Validation errors: {len(body.get('detail', []))}")


def test_response_structure():
    section("7. التحقق من هيكل الاستجابة (جميع الحقول المطلوبة)")
    code, body = post("/v1/process-voice", {
        "db_uuid": "odoo-uuid-court-custom-67890",
        "res_model": "sale.order",
        "res_id": None,
        "model_schema": {"name": {"type": "char", "string": "الاسم"}},
        "audio_base64": text_to_b64("x"),
        "mock_speech_text": "أنشئ سجلاً جديداً",
    })
    check(code == 200, f"HTTP 200")
    for field in ("intent", "extracted_data", "feedback_message"):
        check(field in body, f"حقل '{field}' موجود في الاستجابة")
    check("report_instruction" in body, "حقل 'report_instruction' موجود (يمكن أن يكون null)")
    valid_intents = {"create", "update", "navigate", "report", "extract"}
    check(body["intent"] in valid_intents, f"intent='{body['intent']}' ضمن القيم الصحيحة")
    print(f"  ℹ️  intent={body['intent']}")


# ─── main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🚀 بدء اختبارات Odoo AI Voice Proxy Gateway")
    print("=" * 55)

    test_health()
    test_unauthorized_uuid()
    test_scenario_1_report()
    test_scenario_2_update()
    test_scenario_3_create()
    test_missing_fields()
    test_response_structure()

    print(f"\n{'='*55}")
    print("  🎉 جميع الاختبارات اجتازت بنجاح!")
    print(f"{'='*55}\n")
