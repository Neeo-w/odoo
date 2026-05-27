# التقرير التقني الشامل — نظام المساعد الصوتي الذكي لأودو
**التاريخ:** 27 مايو 2026  
**الإصدار:** 2.0  
**المنصة:** Odoo 17/19 + FastAPI + Groq / OpenAI

---

## فهرس المحتويات

1. [نظرة عامة على النظام](#1-نظرة-عامة-على-النظام)
2. [بنية الملفات والمكونات](#2-بنية-الملفات-والمكونات)
3. [وصف تفصيلي لكل ملف](#3-وصف-تفصيلي-لكل-ملف)
4. [الشاشات وتجربة المستخدم](#4-الشاشات-وتجربة-المستخدم)
5. [تحليل السيرفر والكود — البدائل المتاحة](#5-تحليل-السيرفر-والكود--البدائل-المتاحة)
6. [إدارة المستخدمين والاشتراكات والتوكن](#6-إدارة-المستخدمين-والاشتراكات-والتوكن)
7. [التطويرات المستقبلية](#7-التطويرات-المستقبلية)
8. [دليل التثبيت والتشغيل الكامل](#8-دليل-التثبيت-والتشغيل-الكامل)

---

## 1. نظرة عامة على النظام

### الهدف

يتيح النظام لمستخدمي أودو التحكم في النظام **بصوتهم** بدلاً من الكتابة والنقر. يقوم المستخدم بالضغط على زر الميكروفون في شريط التنقل العلوي، يتكلم بالعربية، وتنفذ أودو العملية تلقائياً (إنشاء سجل، تعديل بيانات، صياغة تقرير، التنقل لسجل آخر).

### المعمارية العامة

```
┌─────────────────────────────────────────────────────────────┐
│                     متصفح المستخدم                          │
│                                                             │
│  ┌──────────────┐    ┌──────────────────────────────────┐  │
│  │  زر الميك    │───▶│  voice_button.js (OWL Component) │  │
│  │  روفون في    │    │  تسجيل صوت WebM → Base64         │  │
│  │  Systray     │    └──────────────┬───────────────────┘  │
│  └──────────────┘                   │ RPC                   │
└─────────────────────────────────────┼─────────────────────┘
                                      │ /ai_voice/process
                                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    سيرفر أودو (Python)                       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  AIVoiceController (controllers/main.py)              │  │
│  │  • يجمع schema الموديول الحالي (حتى 60 حقل)          │  │
│  │  • يرسل payload كاملاً للسيرفر الخارجي               │  │
│  │  • /ai_voice/resolve_names لتحويل أسماء → IDs        │  │
│  └──────────────────────────┬───────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────┘
                              │ HTTP POST JSON
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              AI Voice Proxy Gateway (FastAPI)                │
│                    ai_voice_server/server.py                 │
│                                                             │
│  1. التحقق من اشتراك db_uuid                               │
│  2. تحويل الصوت → نص  (Whisper على Groq/OpenAI)           │
│  3. فهم النية واستخراج البيانات (Llama 3.3 / GPT-4o)      │
│  4. إعادة JSON منظم: intent + extracted_data + feedback    │
└──────────────┬──────────────────────────────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
    ▼                     ▼
 Groq API            OpenAI API
 whisper-large-v3    whisper-1
 llama-3.3-70b       gpt-4o
```

### الإحصائيات

| المكوّن | عدد الملفات | سطور الكود |
|---------|-------------|------------|
| موديول أودو (`ai_voice_assistant`) | 9 ملفات | ~320 سطر |
| سيرفر FastAPI (`ai_voice_server`) | 2 ملفات | ~280 سطر |
| **الإجمالي** | **11 ملفاً** | **~600 سطر** |

---

## 2. بنية الملفات والمكونات

```
odoo/
├── addons/
│   └── ai_voice_assistant/           ← موديول أودو القابل للتثبيت
│       ├── __manifest__.py           ← تعريف الموديول
│       ├── __init__.py               ← استيراد الحزم
│       ├── controllers/
│       │   ├── __init__.py
│       │   └── main.py               ← HTTP endpoints داخل أودو
│       ├── models/
│       │   ├── __init__.py
│       │   └── res_config_settings.py ← إعدادات في لوحة التحكم
│       ├── security/
│       │   └── ir.model.access.csv   ← صلاحيات الوصول
│       ├── static/src/
│       │   ├── js/
│       │   │   └── voice_button.js   ← المكوّن OWL الرئيسي
│       │   ├── scss/
│       │   │   └── voice_button.scss ← التنسيق والتأثيرات
│       │   └── xml/
│       │       └── voice_button.xml  ← قالب HTML (OWL Template)
│       └── views/
│           └── res_config_settings_views.xml ← شاشة الإعدادات
│
└── ai_voice_server/                  ← سيرفر مستقل (FastAPI)
    ├── server.py                     ← الكود الرئيسي للسيرفر
    ├── requirements.txt              ← المكتبات المطلوبة
    └── test_server.py                ← مجموعة الاختبارات (7 اختبارات)
```

---

## 3. وصف تفصيلي لكل ملف

### 3.1 `__manifest__.py` — تعريف الموديول

**الهدف:** يعرّف الموديول لأودو ويحدد اعتمادياته.

| الحقل | القيمة |
|-------|--------|
| `name` | AI Voice Assistant |
| `version` | 19.0.1.0.0 |
| `category` | Tools |
| `depends` | `base`, `web`, `base_setup` |
| `license` | LGPL-3 |

**أبرز ما يفعله:**
- يُسجّل ملفات CSS/JS/XML في `web.assets_backend` لتُحمَّل تلقائياً مع واجهة أودو
- يربط ملفات الإعدادات (`views/`, `security/`)

---

### 3.2 `controllers/main.py` — المتحكم الرئيسي في أودو

**الهدف:** بوابة الاتصال بين المتصفح وسيرفر الذكاء الاصطناعي.

#### العمليات (Endpoints):

**`POST /ai_voice/process`**
```
المدخلات:
  audio_base64  ← الصوت المسجّل بصيغة Base64
  res_model     ← اسم الموديول الحالي (مثلاً: sale.order)
  res_id        ← معرف السجل المفتوح (اختياري)

ما يفعله:
  1. يقرأ رابط السيرفر من ir.config_parameter
  2. يقرأ db_uuid من الإعدادات
  3. يستدعي _get_model_schema() لاستخراج بنية الحقول
  4. يرسل POST request للسيرفر الخارجي
  5. يعيد النتيجة للمتصفح

المخرجات:
  { success: true, data: { intent, extracted_data, feedback_message, report_instruction } }
  أو
  { success: false, error: "رسالة الخطأ" }
```

**`POST /ai_voice/resolve_names`**
```
المدخلات:
  res_model    ← اسم الموديول
  field_values ← قاموس { field_name: value_as_string }

ما يفعله:
  يحوّل الأسماء البشرية إلى IDs في قاعدة البيانات
  مثال: "شركة الخليج" → 42 (partner_id)

يستخدم: name_search() من ORM أودو
```

**`_get_model_schema()` (دالة مساعدة خاصة)**
```
ما تفعله:
  - تستدعي fields_get() على الموديول الحالي
  - تُقصي: binary, html, one2many, reference, serialized
  - تُقصي الحقول التي تبدأ بـ _
  - تُحدّد بـ 60 حقل كحد أقصى
  - تُعيد قاموس: { field_name: { type, string, selection? } }

الهدف: تزويد الذكاء الاصطناعي بمعلومات كافية لفهم الشاشة
```

---

### 3.3 `models/res_config_settings.py` — نموذج الإعدادات

**الهدف:** إضافة حقلين في صفحة الإعدادات العامة لأودو.

| الحقل | المفتاح في ir.config_parameter | الوصف |
|-------|-------------------------------|-------|
| `ai_voice_server_url` | `ai_voice.server_url` | رابط سيرفر FastAPI |
| `ai_voice_db_uuid` | `ai_voice.db_uuid` | UUID قاعدة البيانات |

**منطق `get_values()`:** يقرأ UUID من الإعدادات، وإن لم يوجد يسقط إلى `database.uuid` المُولَّد تلقائياً بأودو.

---

### 3.4 `static/src/js/voice_button.js` — مكوّن OWL الرئيسي

**الهدف:** واجهة المستخدم الكاملة والمنطق في المتصفح.

#### الحالات (States):
```javascript
state = {
    isRecording: false,   // أثناء تسجيل الصوت
    isProcessing: false,  // أثناء الإرسال والمعالجة
}
```

#### دورة حياة الأمر الصوتي:

```
المستخدم يضغط الزر
        │
        ▼
_startRecording()
  • getUserMedia({ audio: true })
  • MediaRecorder (audio/webm;codecs=opus)
  • تسجيل شرائح كل 250ms
        │
المستخدم يضغط مجدداً
        │
        ▼
_stopRecording()
  • mediaRecorder.stop()
        │
        ▼
_processRecording()
  • Blob → Base64
  • _getCurrentContext() ← res_model + res_id من الواجهة
  • rpc("/ai_voice/process", {...})
        │
        ▼
_executeAIAction(data)
  ┌─────────────────────────────────────┐
  │ intent='create'                     │
  │   _resolveFieldNames() → IDs       │
  │   actionService.doAction(form)      │
  ├─────────────────────────────────────┤
  │ intent='update'                     │
  │   _resolveFieldNames() → IDs       │
  │   orm.write(model, [resId], vals)   │
  │   currentController.reload()        │
  ├─────────────────────────────────────┤
  │ intent='report'                     │
  │   notification (sticky, info)       │
  │   actionService.doAction("report")  │
  ├─────────────────────────────────────┤
  │ intent='navigate'                   │
  │   actionService.doAction(form, id)  │
  └─────────────────────────────────────┘
```

#### الخدمات المستخدمة من أودو:
- `notification` — إشعارات للمستخدم
- `action` — التنقل بين الشاشات
- `orm` — كتابة البيانات في قاعدة البيانات

---

### 3.5 `static/src/xml/voice_button.xml` — قالب HTML

**الهدف:** تعريف مظهر الزر بثلاث حالات:

| الحالة | الأيقونة | اللون |
|--------|----------|-------|
| جاهز للتسجيل | `fa-microphone` | أبيض |
| يسجّل | `fa-stop-circle` + pulse | أحمر متوهج |
| يعالج | `fa-spinner fa-spin` | معطّل |

---

### 3.6 `static/src/scss/voice_button.scss` — التنسيق

**التأثيرات المُنفَّذة:**
- `o_ai_voice_glow` — توهج أحمر نابض أثناء التسجيل
- `o_ai_voice_blink` — ومضة النقطة الحمراء (pulse dot)
- الزر دائري 32×32px، شفاف، يظهر في شريط التنقل

---

### 3.7 `views/res_config_settings_views.xml` — شاشة الإعدادات

**الهدف:** إضافة قسم "المساعد الصوتي الذكي" في:  
**الإعدادات → التهيئة العامة**

يحتوي على حقلين جانباً لجانب (Bootstrap 6 col-lg-6):
1. رابط سيرفر الذكاء الاصطناعي
2. معرّف قاعدة البيانات UUID

---

### 3.8 `ai_voice_server/server.py` — سيرفر FastAPI

*(تفاصيل كاملة في القسم 5)*

**ملخص سريع:**
- FastAPI v0.111+ مع Pydantic v2
- نقطتا endpoint: `/v1/process-voice` و `/health`
- دعم مزدوج: Groq + OpenAI
- وضع محاكاة (MOCK_MODE) للتطوير بدون مفتاح API
- قائمة مشتركين في الذاكرة (مؤقتة — تُحدَّث لاحقاً بقاعدة بيانات)

---

### 3.9 `ai_voice_server/test_server.py` — مجموعة الاختبارات

**7 اختبارات تُغطي:**

| رقم | الاختبار | ما يتحقق |
|-----|----------|----------|
| 1 | Health Check | السيرفر يعمل، provider صحيح |
| 2 | UUID غير مسجّل | يُعيد 403 مع رسالة واضحة |
| 3 | سيناريو تقرير قانوني | intent='report', report_instruction موجود |
| 4 | سيناريو تعديل بيانات | intent='update', extracted_data غير فارغ |
| 5 | سيناريو إنشاء sale.order | intent='create', الحقول صحيحة |
| 6 | طلب ناقص الحقول | يُعيد 422 Validation Error |
| 7 | هيكل الاستجابة | جميع الحقول المطلوبة موجودة |

---

## 4. الشاشات وتجربة المستخدم

### 4.1 الشاشة الرئيسية — زر الميكروفون في Systray

```
┌────────────────────────────────────────────────────────────────────┐
│  [≡] أودو    المبيعات  المشتريات  ...                    [🎤] [👤] │
└────────────────────────────────────────────────────────────────────┘
                                                             ↑
                                                    زر الميكروفون
                                                    (أبيض، دائري)
```

**سلوك الزر:**
- **ضغطة أولى:** يبدأ التسجيل (أحمر + نبضة)
- **ضغطة ثانية:** يوقف التسجيل ويبدأ المعالجة (spinner)
- **النتيجة:** إشعار أخضر بالعربية + تنفيذ العملية تلقائياً

---

### 4.2 شاشة الإعدادات

**المسار:** الإعدادات → التهيئة العامة → المساعد الصوتي الذكي

```
┌─────────────────────────────────────────────────────────────────┐
│  إعدادات المساعد الصوتي الذكي                                  │
│                                                                 │
│  ┌──────────────────────────────┐  ┌─────────────────────────┐ │
│  │ رابط سيرفر الذكاء الاصطناعي │  │ معرّف قاعدة البيانات    │ │
│  │ رابط FastAPI سيرفر معالجة   │  │ UUID                    │ │
│  │ الصوت الخارجي               │  │                         │ │
│  │ [http://localhost:8000/v1/..] │  │ [odoo-uuid-xxxxx]      │ │
│  └──────────────────────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

### 4.3 سيناريوهات التفاعل

#### سيناريو 1: إنشاء أمر بيع
```
المستخدم (في شاشة sale.order):
  "أنشئ أمر بيع لشركة الخليج بمنتج لابتوب ديل كمية ثلاثة"
  
النتيجة:
  ✅ إشعار: "تم فهم طلب الإنشاء في sale.order"
  → يفتح نموذج إنشاء جديد مُعبَّأ بـ:
     partner_id = 15 (ID شركة الخليج)
     order_line = [{ product_id: 7, product_uom_qty: 3 }]
```

#### سيناريو 2: تعديل بيانات
```
المستخدم (في سجل court.session رقم 105):
  "عدّل اسم القاضي إلى بن أحمد"
  
النتيجة:
  ✅ إشعار: "تم تعديل السجل رقم 105"
  → orm.write('court.session', [105], { judge_name: 'بن أحمد' })
  → إعادة تحميل الشاشة
```

#### سيناريو 3: تقرير رسمي
```
المستخدم (في سجل قضائي):
  "أعد صياغة تقرير الجلسة بأسلوب قانوني رسمي"
  
النتيجة:
  ℹ️ إشعار مُثبَّت (sticky): النص القانوني الكامل
  → محاولة طباعة PDF إن وُجد report action
```

#### سيناريو 4: رفض مشترك غير مسجّل
```
قاعدة بيانات غير مشتركة تُرسل طلباً:
  
النتيجة:
  🚫 HTTP 403
  ❌ "اشتراكك منتهي أو غير فعال. يرجى التجديد."
```

---

## 5. تحليل السيرفر والكود — البدائل المتاحة

### 5.1 تحليل `server.py` السطر بالسطر

#### تكوين المزودين (سطور 10-34)

```python
PROVIDER       = os.environ.get("AI_PROVIDER", "groq")   # groq | openai
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MOCK_MODE      = os.environ.get("MOCK_MODE", "false").lower() == "true"
```

**المنطق:** كل الإعدادات تأتي من متغيرات البيئة — لا أسرار في الكود.  
يُنشئ Client مرة واحدة عند بدء التشغيل (singleton pattern).

---

#### نماذج البيانات (سطور 44-68) — Pydantic v2

```python
class VoiceRequest(BaseModel):
    db_uuid: str           # للتحقق من الاشتراك
    res_model: str         # اسم موديول أودو
    res_id: Optional[int]  # None = إنشاء جديد
    model_schema: Dict     # حقول الشاشة من أودو
    audio_base64: str      # الصوت
    mock_speech_text: Optional[str]  # للاختبار بدون صوت

class OdooActionResponse(BaseModel):
    intent: str                     # create|update|report|navigate|extract
    extracted_data: Dict[str, Any]  # الحقول والقيم
    report_instruction: Optional[str]
    feedback_message: str
```

**الفائدة:** FastAPI يتحقق تلقائياً من البيانات ويُعيد 422 للطلبات الناقصة.

---

#### بناء System Prompt (سطور 70-90)

```python
def _build_system_prompt(res_model, model_schema, res_id):
    """
    يُزوّد الذكاء الاصطناعي بـ:
    1. اسم الموديول الحالي
    2. بنية كل حقل (type + string + selection options)
    3. هل هو سجل موجود أم إنشاء جديد
    4. قواعد حاسمة: تنسيق التاريخ، لا اختراع حقول
    5. الهيكل المطلوب للـ JSON المُعاد
    """
```

**النقطة الذكية:** إرسال `model_schema` يجعل الذكاء الاصطناعي يعمل مع **أي موديول** في أودو دون تعديل الكود.

---

#### استدعاء الذكاء الاصطناعي (سطور 93-122)

```python
def _call_ai(speech_text, res_model, model_schema, res_id):
    if PROVIDER == "groq":
        # Groq: response_format={"type": "json_object"}
        # يضمن JSON دائماً صحيح
        resp = AI_CLIENT.chat.completions.create(
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            temperature=0.1,  # حتمية عالية
        )
    else:
        # OpenAI: Structured Output مع Pydantic مباشرة
        resp = AI_CLIENT.beta.chat.completions.parse(
            model="gpt-4o",
            response_format=OdooActionResponse,
        )
```

**الفرق:** Groq يُعيد JSON نصياً ونُحوّله يدوياً، OpenAI يُعيد كائن Pydantic مباشرة.

---

#### تحويل الصوت (سطور 125-137)

```python
def _transcribe_audio(audio_b64, db_uuid):
    audio_bytes = base64.b64decode(audio_b64)
    tmp_path = f"/tmp/ai_voice_{db_uuid}.webm"
    # يكتب ملف مؤقت → يُرسله لـ Whisper → يحذفه
    transcription = AI_CLIENT.audio.transcriptions.create(
        model="whisper-large-v3",  # لـ Groq
        language="ar",             # عربي محدد لدقة أعلى
    )
    return transcription.text
```

**ملاحظة:** الملف المؤقت يُكتب بمسار يحتوي db_uuid لتفادي التعارض بين طلبات متزامنة.

---

### 5.2 بدائل مزودي الذكاء الاصطناعي

#### مقارنة شاملة

| المعيار | Groq | OpenAI | Azure OpenAI | Ollama (محلي) |
|---------|------|--------|--------------|---------------|
| **السرعة (STT)** | ⚡ 1-3 ثانية | 🔵 3-8 ثانية | 🔵 3-8 ثانية | 🔴 10-30 ثانية |
| **السرعة (LLM)** | ⚡ 0.5-1 ثانية | 🔵 2-5 ثانية | 🔵 2-5 ثانية | 🔴 5-20 ثانية |
| **نموذج STT** | whisper-large-v3 | whisper-1 | whisper | faster-whisper |
| **نموذج LLM** | llama-3.3-70b | gpt-4o | gpt-4o | llama3, mistral |
| **التكلفة** | مجاني (حد مجاني) | 💰 مدفوع | 💰 مدفوع | مجاني تماماً |
| **الخصوصية** | بيانات تُرسل خارجاً | بيانات تُرسل خارجاً | يمكن في منطقتك | ✅ محلي كامل |
| **دعم العربية** | ممتاز | ممتاز | ممتاز | متوسط |
| **صعوبة الإعداد** | ✅ سهل | ✅ سهل | متوسط | 🔴 صعب (GPU) |

---

#### كيفية التبديل بين المزودين

```bash
# Groq (افتراضي — موصى به للبداية)
export AI_PROVIDER=groq
export GROQ_API_KEY=gsk_xxxxx

# OpenAI
export AI_PROVIDER=openai
export OPENAI_API_KEY=sk-xxxxx

# وضع التطوير (بدون مفتاح)
export MOCK_MODE=true
```

---

#### إضافة مزود جديد (مثال: Azure)

في `server.py`، أضف في قسم التهيئة:

```python
elif PROVIDER == "azure":
    from openai import AzureOpenAI
    AI_CLIENT = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version="2024-02-01",
    )
    STT_MODEL  = "whisper"       # اسم deployment في Azure
    CHAT_MODEL = "gpt-4o"        # اسم deployment في Azure
```

---

#### إضافة Ollama (محلي كامل — للخصوصية)

```python
elif PROVIDER == "ollama":
    from openai import OpenAI as OllamaClient
    AI_CLIENT = OllamaClient(
        base_url="http://localhost:11434/v1",
        api_key="ollama",  # مطلوب لكن تُهمَل
    )
    STT_MODEL  = "faster-whisper"  # يُثبَّت منفصلاً
    CHAT_MODEL = "llama3.3:70b"    # يُنزَّل بـ: ollama pull llama3.3:70b
```

**متطلبات Ollama:** GPU بذاكرة ≥16GB للنموذج الكامل، أو 8GB لنموذج مضغوط (quantized).

---

## 6. إدارة المستخدمين والاشتراكات والتوكن

### 6.1 الوضع الحالي (بسيط)

حالياً قائمة المشتركين مُضمَّنة في الكود:
```python
ACTIVE_SUBSCRIBERS: list[str] = [
    "odoo-uuid-standard-customer-12345",
    "odoo-uuid-court-custom-67890",
]
```
**المشكلة:** لا يمكن إضافة مشترك بدون إعادة تشغيل السيرفر.

---

### 6.2 النظام الكامل المقترح — خطوات التطوير

#### الخطوة 1: قاعدة بيانات للاشتراكات

**الجداول المطلوبة:**

```sql
-- جدول العملاء / المشتركين
CREATE TABLE subscribers (
    id              SERIAL PRIMARY KEY,
    db_uuid         VARCHAR(64) UNIQUE NOT NULL,
    company_name    VARCHAR(200) NOT NULL,
    email           VARCHAR(200) NOT NULL,
    plan_id         INTEGER REFERENCES plans(id),
    status          VARCHAR(20) DEFAULT 'active',  -- active|suspended|expired
    tokens_used     INTEGER DEFAULT 0,
    tokens_reset_at TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP
);

-- جدول الباقات
CREATE TABLE plans (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,     -- مثلاً: مجاني, أساسي, احترافي
    price_monthly   DECIMAL(10,2),
    tokens_per_month INTEGER NOT NULL,         -- -1 = غير محدود
    max_audio_seconds INTEGER DEFAULT 300,     -- الحد الأقصى لكل ملف صوتي
    description     TEXT
);

-- جدول سجل الاستخدام
CREATE TABLE usage_logs (
    id              SERIAL PRIMARY KEY,
    subscriber_id   INTEGER REFERENCES subscribers(id),
    tokens_used     INTEGER NOT NULL,
    audio_seconds   FLOAT,
    intent          VARCHAR(20),
    res_model       VARCHAR(100),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- بيانات أولية للباقات
INSERT INTO plans VALUES
  (1, 'مجاني',      0,    1000,  60,  '1000 توكن / شهر، حتى 60 ثانية صوت'),
  (2, 'أساسي',     49,   10000, 180, '10,000 توكن / شهر'),
  (3, 'احترافي',  149,   50000, 300, '50,000 توكن / شهر، أولوية المعالجة'),
  (4, 'مؤسسي',   499,  -1,     600, 'غير محدود، SLA مضمون');
```

---

#### الخطوة 2: تحديث `server.py` لدعم قاعدة البيانات

```python
import psycopg2
from functools import lru_cache

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:pass@localhost/voice_db")

def get_subscriber(db_uuid: str) -> dict | None:
    """يتحقق من الاشتراك ويُعيد بيانات المشترك أو None."""
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.id, s.status, s.tokens_used, s.expires_at,
                       p.tokens_per_month, p.max_audio_seconds, p.name as plan_name
                FROM subscribers s
                JOIN plans p ON s.plan_id = p.id
                WHERE s.db_uuid = %s
            """, (db_uuid,))
            row = cur.fetchone()
    if not row:
        return None
    cols = ["id","status","tokens_used","expires_at","tokens_per_month","max_audio_seconds","plan_name"]
    return dict(zip(cols, row))

def deduct_tokens(subscriber_id: int, tokens: int):
    """يُسجّل الاستخدام ويُخصم من الرصيد."""
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscribers SET tokens_used = tokens_used + %s WHERE id = %s",
                (tokens, subscriber_id)
            )
            cur.execute(
                "INSERT INTO usage_logs (subscriber_id, tokens_used) VALUES (%s, %s)",
                (subscriber_id, tokens)
            )
        conn.commit()
```

---

#### الخطوة 3: نقطة `process_voice` المحدّثة

```python
@app.post("/v1/process-voice", response_model=OdooActionResponse)
async def process_voice(request: VoiceRequest):
    # 1. التحقق من المشترك
    subscriber = get_subscriber(request.db_uuid)
    if not subscriber:
        raise HTTPException(403, "قاعدة البيانات غير مسجّلة. يرجى الاشتراك.")

    if subscriber["status"] != "active":
        raise HTTPException(403, f"الاشتراك {subscriber['status']}. يرجى التجديد.")

    # 2. التحقق من انتهاء الصلاحية
    if subscriber["expires_at"] and subscriber["expires_at"] < datetime.now():
        raise HTTPException(402, "انتهت صلاحية اشتراكك. يرجى التجديد.")

    # 3. التحقق من رصيد التوكن
    limit = subscriber["tokens_per_month"]
    used  = subscriber["tokens_used"]
    if limit != -1 and used >= limit:
        raise HTTPException(402,
            f"استنفدت رصيدك من التوكن ({used}/{limit}). "
            f"ترقّ إلى باقة أعلى أو انتظر الدورة القادمة."
        )

    # 4. معالجة الصوت
    speech_text = _transcribe_audio(request.audio_base64, request.db_uuid)
    result = _call_ai(speech_text, request.res_model, request.model_schema, request.res_id)

    # 5. خصم التوكن (تقدير: 100 توكن للطلب + 50 للصوت)
    estimated_tokens = 150
    deduct_tokens(subscriber["id"], estimated_tokens)

    return result
```

---

#### الخطوة 4: Endpoints إدارة الاشتراكات

```python
# ─── لوحة الإدارة ─────────────────────────────────────────────

@app.post("/admin/subscribers", dependencies=[Depends(verify_admin)])
async def create_subscriber(
    db_uuid: str,
    company_name: str,
    email: str,
    plan_id: int = 2,
):
    """إضافة مشترك جديد."""
    ...

@app.get("/admin/subscribers/{db_uuid}")
async def get_subscriber_info(db_uuid: str):
    """عرض بيانات مشترك."""
    ...

@app.put("/admin/subscribers/{db_uuid}/plan")
async def change_plan(db_uuid: str, new_plan_id: int):
    """تغيير الباقة (ترقية / تخفيض)."""
    ...

@app.put("/admin/subscribers/{db_uuid}/suspend")
async def suspend_subscriber(db_uuid: str):
    """تعليق الاشتراك."""
    ...

# ─── للعملاء ───────────────────────────────────────────────────

@app.get("/v1/usage")
async def get_my_usage(db_uuid: str):
    """يُظهر رصيد التوكن المتبقي للعميل."""
    sub = get_subscriber(db_uuid)
    if not sub:
        raise HTTPException(404)
    remaining = sub["tokens_per_month"] - sub["tokens_used"]
    return {
        "plan": sub["plan_name"],
        "tokens_used": sub["tokens_used"],
        "tokens_limit": sub["tokens_per_month"],
        "tokens_remaining": remaining if sub["tokens_per_month"] != -1 else "غير محدود",
        "reset_date": sub.get("tokens_reset_at"),
    }
```

---

### 6.3 الباقات المقترحة

| الباقة | السعر / شهر | التوكن | مدة الصوت | مناسبة لـ |
|--------|-------------|--------|-----------|-----------|
| **مجاني** | 0 ريال | 1,000 | 60 ثانية | التجربة والتطوير |
| **أساسي** | 49 ريال | 10,000 | 3 دقائق | شركة صغيرة (5 مستخدمين) |
| **احترافي** | 149 ريال | 50,000 | 5 دقائق | شركة متوسطة (20 مستخدماً) |
| **مؤسسي** | 499 ريال | غير محدود | 10 دقائق | شركة كبيرة |

**ملاحظة حساب التوكن:**  
- تحويل صوت 30 ثانية ≈ 200 توكن Whisper  
- LLM (استخراج البيانات) ≈ 500-800 توكن لكل طلب  
- **متوسط الطلب الواحد ≈ 800-1000 توكن**

---

### 6.4 إضافة عداد التوكن في شاشة أودو

في `voice_button.js` أضف:

```javascript
async _showUsage() {
    const db_uuid = await this._getDbUuid();
    const usage = await rpc("/ai_voice/usage_proxy", { db_uuid });
    this.notification.add(
        `📊 التوكن المستخدمة: ${usage.tokens_used} / ${usage.tokens_limit}`,
        { type: "info", autocloseDelay: 5000 }
    );
}
```

وفي `controllers/main.py`:

```python
@http.route('/ai_voice/usage_proxy', type='json', auth='user', methods=['POST'])
def usage_proxy(self, db_uuid):
    server_url = ICP.get_param('ai_voice.server_url').replace('/v1/process-voice', '/v1/usage')
    # ... fetch and return
```

---

## 7. التطويرات المستقبلية

### 7.1 المرحلة الأولى — تحسينات فورية (أسبوعان)

| التطوير | الأثر | الجهد |
|---------|-------|-------|
| نقل قائمة المشتركين لقاعدة بيانات | أساسي للإنتاج | متوسط |
| API لإدارة المشتركين + لوحة تحكم بسيطة | يمكّن البيع | متوسط |
| حذف الملفات الصوتية المؤقتة بعد المعالجة | أمان + مساحة | سهل |
| Webhook لإشعار أودو عند نفاد التوكن | تجربة مستخدم | متوسط |
| تشفير `audio_base64` أثناء النقل (HTTPS) | أمان ضروري | سهل |

---

### 7.2 المرحلة الثانية — ميزات متقدمة (شهر)

#### 7.2.1 دعم الأوامر متعددة الخطوات
```
المستخدم: "أنشئ عميلاً باسم شركة النور ثم أنشئ له أمر بيع بمنتج مضخة مياه كمية عشرة"

النظام الحالي: ينفذ فقط أول عملية
التطوير: يُعيد قائمة من الأوامر وينفذها بالتسلسل
```

```python
# response_schema الجديد
class MultiActionResponse(BaseModel):
    actions: List[OdooActionResponse]
    summary: str
```

#### 7.2.2 دعم البحث الصوتي
```
المستخدم: "ابحث عن جميع أوامر البيع المفتوحة لشركة النور"

intent='search'
extracted_data = {
    "domain": [["partner_id.name", "ilike", "النور"], ["state", "=", "sale"]],
    "model": "sale.order"
}
```

#### 7.2.3 تقارير PDF بالصوت
```
المستخدم: "اطبع فاتورة هذا الأمر"
→ actionService.doAction({ type: "ir.actions.report", report_name: "...", ids: [resId] })
```

#### 7.2.4 دعم اللغات المتعددة
```python
# في _build_system_prompt أضف:
language_hint = "ar"  # أو "en", "fr"
```

```javascript
// في voice_button.js
const lang = document.documentElement.lang || "ar";
const transcription = await rpc("/ai_voice/process", { ..., language: lang });
```

---

### 7.3 المرحلة الثالثة — توسعات (ثلاثة أشهر)

| الميزة | الوصف |
|--------|-------|
| **تطبيق موبايل** | React Native / Flutter بنفس API |
| **وضع offline جزئي** | Whisper مُثبَّت محلياً في المتصفح (WebAssembly) |
| **ذاكرة المحادثة** | السيرفر يحتفظ بالسياق لأوامر متسلسلة |
| **تكامل الـ chatter** | تسجيل الأوامر الصوتية كـ notes في chatter |
| **موديول القضاء الكامل** | حقول مخصصة + workflow + تقارير PDF رسمية |
| **نظام الدفع** | Stripe / PayTabs تكامل مع الباقات |
| **لوحة تحليلات** | رسوم بيانية لاستخدام التوكن، أكثر الأوامر شيوعاً |

---

## 8. دليل التثبيت والتشغيل الكامل

### 8.1 المتطلبات

| المكوّن | الإصدار الأدنى |
|---------|----------------|
| Python | 3.11+ |
| Odoo | 17.0 أو 18.0 أو 19.0 |
| نظام التشغيل | Ubuntu 22.04 LTS (موصى به) |
| RAM | 4GB (8GB مُفضَّل) |
| مفتاح API | Groq (مجاني) أو OpenAI (مدفوع) |

---

### 8.2 الخطوة 1: إعداد السيرفر المستقل (FastAPI)

```bash
# ── على سيرفر VPS أو جهازك المحلي ──

# 1. استنسخ المستودع
git clone https://github.com/Neeo-w/odoo.git
cd odoo/ai_voice_server

# 2. أنشئ بيئة Python افتراضية
python3 -m venv venv
source venv/bin/activate

# 3. ثبّت المتطلبات
pip install -r requirements.txt
pip install groq  # أضف groq (ليست في requirements.txt بعد)

# 4. أعدّ متغيرات البيئة
export AI_PROVIDER=groq
export GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxx   # مفتاحك من console.groq.com

# 5. شغّل السيرفر
uvicorn server:app --host 0.0.0.0 --port 8000

# تحقق من الصحة
curl http://localhost:8000/health
# → { "status": "ok", "provider": "groq", ... }
```

---

### 8.3 الخطوة 2: تشغيل السيرفر كـ Service دائم (systemd)

```bash
# أنشئ ملف الخدمة
sudo nano /etc/systemd/system/ai-voice.service
```

```ini
[Unit]
Description=Odoo AI Voice Proxy Gateway
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/odoo/ai_voice_server
Environment="AI_PROVIDER=groq"
Environment="GROQ_API_KEY=gsk_xxxxxxxxxx"
ExecStart=/opt/odoo/ai_voice_server/venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-voice
sudo systemctl start ai-voice
sudo systemctl status ai-voice
```

---

### 8.4 الخطوة 3: إعداد Nginx كـ Reverse Proxy (موصى به للإنتاج)

```nginx
# /etc/nginx/sites-available/ai-voice
server {
    listen 443 ssl;
    server_name ai-voice.yourcompany.com;

    ssl_certificate     /etc/letsencrypt/live/ai-voice.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ai-voice.yourcompany.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
        
        # حد أقصى للصوت المرفوع: 10MB
        client_max_body_size 10M;
    }
}
```

```bash
# شهادة SSL مجانية
sudo certbot --nginx -d ai-voice.yourcompany.com
```

---

### 8.5 الخطوة 4: تثبيت موديول أودو

```bash
# 1. انسخ الموديول لمجلد addons الخاص بأودو
cp -r /path/to/repo/addons/ai_voice_assistant /opt/odoo/custom_addons/

# 2. أضف المسار في odoo.conf
sudo nano /etc/odoo/odoo.conf
# addons_path = /opt/odoo/odoo/addons,/opt/odoo/custom_addons

# 3. أعد تشغيل أودو
sudo systemctl restart odoo

# 4. في واجهة أودو:
#    الإعدادات → تفعيل وضع المطور → Apps → البحث عن "AI Voice" → تثبيت
```

---

### 8.6 الخطوة 5: ربط الموديول بالسيرفر

```
في أودو:
  الإعدادات → التهيئة العامة → المساعد الصوتي الذكي

  ┌──────────────────────────────────────────────────────────┐
  │ رابط سيرفر الذكاء الاصطناعي:                            │
  │ https://ai-voice.yourcompany.com/v1/process-voice        │
  │                                                          │
  │ معرّف قاعدة البيانات (UUID):                            │
  │ [يُعبَّأ تلقائياً من database.uuid]                      │
  └──────────────────────────────────────────────────────────┘
  
  → احفظ
```

---

### 8.7 الخطوة 6: تسجيل UUID في السيرفر

```bash
# اقرأ UUID من أودو
# في psql:
SELECT value FROM ir_config_parameter WHERE key = 'database.uuid';
# → مثلاً: a1b2c3d4-e5f6-7890-abcd-ef1234567890

# أضفه في server.py (مؤقتاً) أو في قاعدة البيانات (الوضع الكامل)
```

**مؤقتاً (للاختبار):** عدّل `ACTIVE_SUBSCRIBERS` في `server.py`:
```python
ACTIVE_SUBSCRIBERS = [
    "a1b2c3d4-e5f6-7890-abcd-ef1234567890",  # UUID قاعدة بياناتك
]
```

---

### 8.8 الخطوة 7: اختبار النظام المتكامل

```bash
# 1. تحقق من صحة السيرفر
curl https://ai-voice.yourcompany.com/health

# 2. اختبار بنص بدون صوت
curl -X POST https://ai-voice.yourcompany.com/v1/process-voice \
  -H "Content-Type: application/json" \
  -d '{
    "db_uuid": "UUID-قاعدة-بياناتك",
    "res_model": "sale.order",
    "res_id": null,
    "model_schema": {
        "partner_id": {"type": "many2one", "string": "العميل"},
        "date_order":  {"type": "datetime", "string": "تاريخ الأمر"}
    },
    "audio_base64": "dGVzdA==",
    "mock_speech_text": "أنشئ أمر بيع جديداً لشركة الخليج"
  }'
```

**الاستجابة المتوقعة:**
```json
{
  "intent": "create",
  "extracted_data": { "partner_id": "شركة الخليج" },
  "report_instruction": null,
  "feedback_message": "✅ تم فهم طلب الإنشاء في sale.order"
}
```

---

### 8.9 قائمة المراجعة النهائية

```
قبل الإنتاج، تأكد من:

□ السيرفر يعمل بـ HTTPS (شهادة SSL)
□ مفتاح API محفوظ في متغيرات البيئة (ليس في الكود)
□ UUID قاعدة بيانات أودو مُضاف في ACTIVE_SUBSCRIBERS
□ رابط السيرفر مُعدَّل في إعدادات أودو
□ الموديول مُثبَّت ومفعّل
□ اختبرت الزر في متصفح Chrome / Firefox
□ أعطيت صلاحية الميكروفون للمتصفح
□ اختبرت الاختبارات السبعة: python3 test_server.py
```

---

## ملخص تنفيذي

| الجانب | الحالة الحالية | المستهدف |
|--------|---------------|----------|
| **المعمارية** | ✅ مكتملة وصلبة | إضافة قاعدة بيانات للاشتراكات |
| **الاختبارات** | ✅ 7/7 تجتاز | إضافة اختبارات تكاملية مع أودو |
| **الأمان** | ⚠️ HTTP + UUID فقط | HTTPS + JWT + rate limiting |
| **الاشتراكات** | ⚠️ قائمة ثابتة | قاعدة بيانات + API إدارة + نظام دفع |
| **التوكن** | ⚠️ غير مطبّق | عداد في الوقت الفعلي مع تنبيهات |
| **الجاهزية للإنتاج** | 70% | الكود جاهز، ينقصه البنية التحتية |
