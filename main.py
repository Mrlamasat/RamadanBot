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
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")
SECOND_CHANNEL = os.environ.get("SECOND_CHANNEL", "RamadanSeries26").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== تهيئة قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, ep_num INTEGER, status TEXT)''')
    
    cursor.execute("PRAGMA table_info(videos)")
    columns = [col[1] for col in cursor.fetchall()]
    for col_name in ["duration", "title", "ep_num"]:
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE videos ADD COLUMN {col_name} TEXT")
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=True):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    res = cursor.fetchall() if fetch else None
    conn.close()
    return res

# 1. استقبال الفيديو
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration_sec = message.video.duration if message.video else 0
    mins, secs = divmod(duration_sec, 60)
    duration_str = f"{mins}:{secs:02d} دقيقة"
    
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
               (str(message.id), duration_str, "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو\n⏱ المدة: {duration_str}\n\nالآن أرسل **البوستر**.")

# 2. استقبال البوستر
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم ربط البوستر.\nالآن أرسل **رقم الحلقة**:")

# 3. النشر المزدوج في القناتين
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id, poster_id, duration FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    
    v_id, p_id, duration = res[0]
    ep_num = message.text
    db_execute("UPDATE videos SET ep_num = ?, status = 'posted' WHERE v_id = ?", (ep_num, v_id), fetch=False)
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    # التنسيق المطلوب
    caption_text = (f"🎬 **الحلقة {ep_num}**\n"
                    f"⏱ المـدة: {duration}\n"
                    f"✨ الجـودة: HD\n\n"
                    f"📥 مشاهدة الآن")
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشـاهدة الآن", url=link)],
        [InlineKeyboardButton("🔥 أعجبتني", callback_data="like"), 
         InlineKeyboardButton("⭐️ 9.5/10", callback_data="rate")]
    ])
    
    # النشر في القناة الأولى
    await client.send_photo(f"@{PUBLIC_CHANNEL}", photo=p_id, caption=caption_text, reply_markup=buttons)
    
    # النشر في القناة الثانية
    try:
        await client.send_photo(f"@{SECOND_CHANNEL}", photo=p_id, caption=caption_text, reply_markup=buttons)
        await message.reply_text(f"✅ تم النشر بنجاح في القناتين!")
    except Exception as e:
        await message.reply_text(f"✅ نُشر في الأولى، وفشل في الثانية (تأكد من أن البوت مشرف هناك).\nالخطأ: {e}")

# 4. نظام الـ Start للمشتركين
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text("أهلاً بك في بوت المسلسلات! 🌙")
        return
    v_id = message.command[1]
    
    # فحص الاشتراك في القناة الأولى (أو يمكنك فحص القناتين حسب رغبتك)
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", message.from_user.id)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex("^(like|rate)$"))
async def interactions(client, query):
    await query.answer("شكراً لتفاعلك! 🔥", show_alert=False)

@app.on_callback_query(filters.regex(r"^chk_"))
async def chk_callback(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await query.answer("⚠️ اشترك أولاً!", show_alert=True)

app.run()
