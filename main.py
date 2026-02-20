import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
# تأكد أن PUBLIC_CHANNEL في Railway بدون علامة @
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== دالة تهيئة قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, status TEXT, ep_num INTEGER, poster_file_id TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                      (user_id INTEGER, poster_id TEXT, UNIQUE(user_id, poster_id))''')
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=True):
    # إضافة timeout لحل مشكلة الثقل وتعليق قاعدة البيانات
    conn = sqlite3.connect("bot_data.db", timeout=20)
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    res = cursor.fetchall() if fetch else None
    conn.close()
    return res

def format_duration(seconds):
    if not seconds: return "غير متوفر"
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d} دقيقة"

# --- دالة فحص الاشتراك (تم تعديلها لتكون مرنة جداً) ---
async def check_user_sub(client, user_id):
    try:
        # إذا كان ايدي القناة أو يوزر نيم
        chat_target = f"@{PUBLIC_CHANNEL}" if not str(PUBLIC_CHANNEL).startswith("-100") else int(PUBLIC_CHANNEL)
        member = await client.get_chat_member(chat_target, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        logging.error(f"Subscription error: {e}")
        # إذا حدث خطأ في الفحص (مثلا البوت ليس ادمن)، نسمح للمستخدم بالمرور مؤقتاً
        return True 
    return False

# ===== استقبال الفيديو والبوستر ورقم الحلقة (نفس نظامك القديم) =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    file = message.video or message.document
    duration_str = format_duration(getattr(file, "duration", 0))
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
               (str(message.id), duration_str, "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {message.id})\nالآن أرسل **البوستر (الصورة)**.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (message.caption or "حلقة جديدة", message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم ربط البوستر.\nالآن أرسل **رقم الحلقة** (أرقام فقط):")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("HD 720p", callback_data=f"q_HD_{v_id}"),
         InlineKeyboardButton("SD 480p", callback_data=f"q_SD_{v_id}")]
    ])
    await message.reply_text(f"✅ سجلت الحلقة {message.text}.\nاختر الجودة للنشر:", reply_markup=markup)

@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id, ep_num FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, p_id, ep_num = res[0]
    
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption_text = (f"🎬 **{title}**\n🔢 رقم الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 [مشاهدة الآن]({link})")
    
    await client.send_photo(f"@{PUBLIC_CHANNEL}", photo=p_id, caption=caption_text,
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
    await query.message.edit_text("✅ تم النشر بنجاح!")

# ===== نظام الـ Start للمشتركين =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت المسلسلات! 🌙")
        return

    v_id = message.command[1]
    
    if await check_user_sub(client, message.from_user.id):
        # مشترك -> ارسل الفيديو وعرض القائمة
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        
        # قائمة الحلقات
        video_data = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if video_data and video_data[0][0]:
            p_id = video_data[0][0]
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC", (p_id,))
            if len(all_ep) > 1:
                btns = []; row = []
                for v_item, num in all_ep:
                    row.append(InlineKeyboardButton(f"الحلقة {num}", url=f"https://t.me/{(await client.get_me()).username}?start={v_item}"))
                    if len(row) == 2: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي حلقات المسلسل:", reply_markup=InlineKeyboardMarkup(btns))
    else:
        # غير مشترك
        btn = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك، أرسل الفيديو", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً لمشاهدة الفيديو.", reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub_callback(client, query):
    v_id = query.data.split("_")[1]
    if await check_user_sub(client, query.from_user.id):
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    else:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)

app.run()
