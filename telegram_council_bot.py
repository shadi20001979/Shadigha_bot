"""
╔══════════════════════════════════════════════════════════════════════════════╗
║     🤖 AI COUNCIL TELEGRAM BOT - روبوت مجلس الخبراء على تليجرام 🤖          ║
║                                                                              ║
║  الميزات:                                                                    ║
║     • الرد على الأسئلة عبر تليجرام                                         ║
║     • استخدام مجلس الخبراء (نموذجين)                                       ║
║     • حفظ تاريخ المحادثات في قاعدة بيانات                                  ║
║     • أوامر مخصصة: /start, /help, /history, /models                        ║
║     • معالجة متوازية للطلبات                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import requests
import time
import json
import sqlite3
import asyncio
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

# ========================================
# 1. الإعدادات الأساسية
# ========================================

# 🔑 مفاتيح API
OPENROUTER_API_KEY = "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"  # ⚠️ ضع مفتاح OpenRouter الخاص بك
TELEGRAM_BOT_TOKEN = "8679386249:AAEhuhkrJAUCgRSV4v6d1OAQ4F6IafflUGc"  # ⚠️ ضع توكن الروبوت من @BotFather

# 🤖 النماذج المجانية
COUNCIL_MODELS = [
    "qwen/qwen3.6-plus:free",
    "arcee-ai/trinity-large-preview:free",
]

CHAIRMAN_MODEL = "arcee-ai/trinity-large-preview:free"

# ⚙️ الإعدادات
TIMEOUT = 45
MAX_ANSWER_LENGTH = 400
PARALLEL_WORKERS = 2

# 📁 قاعدة البيانات
DB_PATH = "telegram_council.db"

# ========================================
# 2. قاعدة البيانات
# ========================================

class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.lock = Lock()
        self.init_db()
    
    def init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # جدول المستخدمين
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    first_seen TEXT,
                    last_seen TEXT
                )
            ''')
            
            # جدول المحادثات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    question TEXT,
                    answer TEXT,
                    models_used TEXT,
                    response_time REAL,
                    timestamp TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
    
    def save_user(self, user_id, username, first_name, last_name):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, first_seen, last_seen)
                VALUES (?, ?, ?, ?, COALESCE((SELECT first_seen FROM users WHERE user_id=?), ?), ?)
            ''', (user_id, username, first_name, last_name, user_id, now, now))
            
            conn.commit()
            conn.close()
    
    def save_conversation(self, user_id, question, answer, models_used, response_time):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO conversations (user_id, question, answer, models_used, response_time, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, question, answer, models_used, response_time, datetime.now().isoformat()))
            conn.commit()
            conn.close()
    
    def get_user_history(self, user_id, limit=10):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT question, answer, timestamp FROM conversations 
                WHERE user_id = ? ORDER BY id DESC LIMIT ?
            ''', (user_id, limit))
            results = cursor.fetchall()
            conn.close()
            return results

db = Database()

# ========================================
# 3. دوال مجلس الخبراء
# ========================================

def get_model_short_name(model):
    return model.replace(":free", "").replace("arcee-ai/", "").replace("qwen/", "")

def ask_model(model, question):
    """إرسال سؤال إلى نموذج معين"""
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": question}]
            },
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return None
    except:
        return None

def run_council_parallel(question):
    """جمع إجابات الخبراء بالتوازي"""
    answers = {}
    
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        future_to_model = {executor.submit(ask_model, model, question): model for model in COUNCIL_MODELS}
        
        for future in future_to_model:
            model = future_to_model[future]
            try:
                answer = future.result(timeout=TIMEOUT)
                if answer:
                    answers[model] = answer
            except:
                pass
    
    return answers

def chairman_synthesis(question, answers):
    """الرئيس يصوغ الإجابة النهائية"""
    if not answers:
        return "❌ عذراً، لم يتمكن أي خبير من الإجابة حالياً. يرجى المحاولة لاحقاً."
    
    synthesis_prompt = f"""السؤال: {question}

إجابات الخبراء:
"""
    for model, answer in answers.items():
        short_name = get_model_short_name(model)
        short_answer = answer[:MAX_ANSWER_LENGTH] if len(answer) > MAX_ANSWER_LENGTH else answer
        synthesis_prompt += f"\nالخبير ({short_name}):\n{short_answer}\n"
    
    synthesis_prompt += "\nقدم إجابة نهائية واحدة شاملة ودقيقة ومنسقة بالعربية."
    
    final_answer = ask_model(CHAIRMAN_MODEL, synthesis_prompt)
    
    if not final_answer and answers:
        best_model = list(answers.keys())[0]
        final_answer = answers[best_model]
    
    return final_answer

def process_question(question):
    """معالجة السؤال وإرجاع الإجابة"""
    start_time = time.time()
    
    answers = run_council_parallel(question)
    final_answer = chairman_synthesis(question, answers)
    
    response_time = time.time() - start_time
    models_used = ",".join([get_model_short_name(m) for m in answers.keys()])
    
    return final_answer, response_time, models_used

# ========================================
# 4. روبوت تليجرام
# ========================================

# إعدادات الروبوت
BOT_TOKEN = TELEGRAM_BOT_TOKEN
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
LAST_UPDATE_ID = 0

def send_message(chat_id, text, parse_mode="HTML"):
    """إرسال رسالة عبر تليجرام"""
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.json()
    except Exception as e:
        print(f"خطأ في الإرسال: {e}")
        return None

def send_typing_action(chat_id):
    """إرسال إشارة الكتابة"""
    url = f"{BASE_URL}/sendChatAction"
    payload = {"chat_id": chat_id, "action": "typing"}
    
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def get_updates(offset=None, timeout=30):
    """جلب التحديثات من تليجرام"""
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": timeout}
    
    if offset:
        params["offset"] = offset
    
    try:
        response = requests.get(url, params=params, timeout=timeout + 5)
        return response.json().get("result", [])
    except Exception as e:
        print(f"خطأ في جلب التحديثات: {e}")
        return []

def format_answer(answer, response_time, models_used):
    """تنسيق الإجابة للعرض في تليجرام"""
    models_text = models_used.replace(",", " + ")
    
    formatted = f"""🤖 **مجلس الخبراء - AI Council**

{answer}

---
⏱️ وقت الاستجابة: {response_time:.1f} ثانية
🧠 النماذج المستخدمة: {models_text}

_تمت الإجابة بواسطة مجلس الخبراء الذكي_"""
    
    return formatted

# ========================================
# 5. معالجة الأوامر
# ========================================

def handle_start(chat_id, user_info):
    """معالجة أمر /start"""
    db.save_user(
        user_id=chat_id,
        username=user_info.get("username", ""),
        first_name=user_info.get("first_name", ""),
        last_name=user_info.get("last_name", "")
    )
    
    welcome_text = """🌿 **مرحباً بك في مجلس الخبراء!** 

أنا روبوت ذكي يعتمد على **مجلس خبراء** من نماذج الذكاء الاصطناعي:
• Qwen 3.6 Plus
• Trinity Large Preview

✨ **ماذا يمكنني أن أقدم لك؟**
• أجب على أسئلتك بدقة عالية
• أستخدم أكثر من نموذج ذكاء اصطناعي
• أقدم إجابات منسقة وشاملة

📌 **الأوامر المتاحة:**
• /start - عرض رسالة الترحيب
• /help - عرض المساعدة
• /history - عرض آخر أسئلتك
• /models - عرض النماذج المستخدمة

💡 **فقط أرسل سؤالك وسأجيب عليه فوراً!**"""
    
    send_message(chat_id, welcome_text)

def handle_help(chat_id):
    """معالجة أمر /help"""
    help_text = """📖 **قائمة المساعدة**

**كيفية الاستخدام:**
أرسل أي سؤال وسيقوم مجلس الخبراء بالإجابة عليه.

**الأمثلة:**
• ما هو الذكاء الاصطناعي؟
• كم ارتفاع برج خليفة؟
• ما هي فوائد الرياضة؟

**الأوامر:**
• /start - ترحيب
• /help - هذه المساعدة
• /history - آخر 5 أسئلة
• /models - النماذج المستخدمة

**ملاحظات:**
• الإجابات تستغرق 20-40 ثانية
• جميع النماذج مجانية
• يتم حفظ تاريخ محادثاتك"""
    
    send_message(chat_id, help_text)

def handle_history(chat_id):
    """معالجة أمر /history"""
    history = db.get_user_history(chat_id, 5)
    
    if not history:
        send_message(chat_id, "📭 لا يوجد تاريخ محادثة بعد. أرسل سؤالك الأول!")
        return
    
    history_text = "📜 **آخر أسئلتك:**\n\n"
    for i, (question, answer, timestamp) in enumerate(history, 1):
        short_answer = answer[:100] + "..." if len(answer) > 100 else answer
        history_text += f"{i}. ❓ {question}\n   💡 {short_answer}\n   📅 {timestamp[:16]}\n\n"
    
    send_message(chat_id, history_text)

def handle_models(chat_id):
    """معالجة أمر /models"""
    models_text = """🧠 **النماذج المستخدمة في المجلس:**

**أعضاء المجلس:**
1. **Qwen 3.6 Plus** 🇨🇳
   • شركة: Alibaba
   • حجم: ~9B معلمة
   • مميزات: سريع، دقة عالية

2. **Trinity Large Preview** 🇺🇸
   • شركة: Arcee AI
   • حجم: ~400B معلمة
   • مميزات: قوي، دقيق

**الرئيس:**
• **Trinity Large Preview** - لدمج الإجابات

✅ جميع النماذج مجانية"""
    
    send_message(chat_id, models_text)

def handle_message(chat_id, text):
    """معالجة الرسائل النصية العادية"""
    # إرسال إشارة الكتابة
    send_typing_action(chat_id)
    
    # إرسال رسالة انتظار
    send_message(chat_id, "🧠 جاري استشارة مجلس الخبراء...")
    
    # معالجة السؤال
    answer, response_time, models_used = process_question(text)
    
    # تنسيق الإجابة
    formatted_answer = format_answer(answer, response_time, models_used)
    
    # إرسال الإجابة
    send_message(chat_id, formatted_answer)
    
    # حفظ المحادثة
    db.save_conversation(chat_id, text, answer, models_used, response_time)

def process_update(update):
    """معالجة تحديث واحد من تليجرام"""
    global LAST_UPDATE_ID
    
    update_id = update.get("update_id")
    if update_id:
        LAST_UPDATE_ID = max(LAST_UPDATE_ID, update_id + 1)
    
    # معالجة الرسائل
    message = update.get("message")
    if not message:
        return
    
    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return
    
    # معلومات المستخدم
    user_info = {
        "username": message.get("from", {}).get("username", ""),
        "first_name": message.get("from", {}).get("first_name", ""),
        "last_name": message.get("from", {}).get("last_name", "")
    }
    
    # النص
    text = message.get("text", "")
    
    # معالجة الأوامر
    if text.startswith("/"):
        if text == "/start":
            handle_start(chat_id, user_info)
        elif text == "/help":
            handle_help(chat_id)
        elif text == "/history":
            handle_history(chat_id)
        elif text == "/models":
            handle_models(chat_id)
        else:
            send_message(chat_id, "⚠️ أمر غير معروف. استخدم /help لعرض الأوامر المتاحة.")
        return
    
    # معالجة الرسائل العادية
    if text.strip():
        handle_message(chat_id, text)

# ========================================
# 6. التشغيل الرئيسي
# ========================================

def main():
    """تشغيل روبوت تليجرام"""
    global LAST_UPDATE_ID
    
    print("\n" + "="*70)
    print("🤖 AI Council Telegram Bot - بدء التشغيل...")
    print("="*70)
    
    # التحقق من التوكن
    if not BOT_TOKEN:
        print("\n❌ خطأ: لم يتم تعيين TELEGRAM_BOT_TOKEN!")
        print("   الرجاء إضافة التوكن في السطر 38 من الملف")
        print("   احصل على التوكن من @BotFather على تليجرام")
        return
    
    # التحقق من مفتاح OpenRouter
    if OPENROUTER_API_KEY == "sk-or-v1-8714cd":
        print("\n⚠️ تنبيه: استخدم مفتاح OpenRouter الافتراضي!")
        print("   يرجى استبداله بمفتاحك الحقيقي للعمل بشكل صحيح")
    
    print(f"\n✅ الروبوت جاهز للعمل!")
    print(f"   🤖 عدد النماذج: {len(COUNCIL_MODELS)}")
    print(f"   👑 الرئيس: {get_model_short_name(CHAIRMAN_MODEL)}")
    print(f"\n📱 ابحث عن الروبوت على تليجرام وأرسل /start")
    print("\n" + "="*70)
    print("🔄 جاري الاستماع للرسائل... (Ctrl+C للإيقاف)")
    print("="*70 + "\n")
    
    try:
        while True:
            updates = get_updates(offset=LAST_UPDATE_ID + 1 if LAST_UPDATE_ID else None, timeout=30)
            
            for update in updates:
                process_update(update)
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\n👋 تم إيقاف الروبوت. إلى اللقاء!")
    except Exception as e:
        print(f"\n❌ خطأ غير متوقع: {e}")

# ========================================
# 7. التشغيل
# ========================================

if __name__ == "__main__":
    main()