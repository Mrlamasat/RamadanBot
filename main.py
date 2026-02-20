import os
import sqlite3
import logging
from datetime import timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ===== Logging =====
logging.basicConfig(level=logging.INFO)

# ===== Config =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("SeriesBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Database =====
def init_db():
    with sqlite3.connect("bot.db") as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            poster_id TEXT,
            ep_num INTEGER,
            quality TEXT,
            duration TEXT,
            status TEXT
        )
        """)
init_db()

def db_execute(q, p=(), fetch=True):
    with sqlite3.connect("bot.db") as conn:
        cur = conn.execute(q, p)
        if fetch: return cur.fetchall()
        conn.commit()

# =========================
# 1️⃣ استقبال الفيديو
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    
    # حساب المدة الفعلية بشكل صحيح
    duration_sec = 0
    if message.video:
        duration_sec = message.video.duration
    elif message.document and hasattr(message.document, "duration"):
        duration_sec = message.document.duration
    
    # تنسيق الوقت ليظهر (ساعة:دقيقة:ثانية) أو (دقيقة:ثانية)
    duration = str(timedelta(seconds=duration_sec)) if duration_sec else "غير معروف"

    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (v_id, duration, "waiting_poster"), fetch=False)
    
    await message.reply_text(f"✅ تم استلام الفيديو.\n⏱ المدة: {duration}\n🖼 أرسل الآن البوستر.")

# =========================
# 2️⃣ استقبال البوستر
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    # جلب آخر فيديو ينتظر بوستر
    res = db_execute("SELECT v_id FROM videos WHERE status='waiting_poster' ORDER BY rowid DESC LIMIT 1")
    if not res: return

    v_id = res[0][0]
    db_execute("UPDATE videos SET poster_id=?, status='waiting_ep' WHERE v_id=?", 
               (message.photo.file_id, v_id), fetch=False)
    
    await message.reply_text("🖼 تم حفظ البوستر.\n🔢 أرسل رقم الحلقة كأرقام فقط.")

# =========================
# 3️⃣ استقبال رقم الحلقة
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep(client, message):
    if not message.text.isdigit():
        await message.reply_text("❌ أرسل رقم الحلقة كأرقام فقط.")
        return

    res = db_execute("SELECT v_id FROM videos WHERE status='waiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num=?, status='waiting_quality' WHERE v_id=?", 
               (int(message.text), v_id), fetch=False)

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 HD", callback_data=f"q_HD_{v_id}"),
         InlineKeyboardButton("📺 SD", callback_data=f"q_SD_{v_id}")]
    ])
    await message.reply_text(f"✨ الحلقة {message.text} جاهزة. اختر الجودة:", reply_markup=buttons)

# =========================
# 4️⃣ اختيار الجودة والنشر
# =========================
@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query: CallbackQuery):
    _, quality, v_id = query.data.split("_")
    
    res = db_execute("SELECT ep_num, poster_id, duration FROM videos WHERE v_id=?", (v_id,))
    if not res: return
    
    ep_num, poster_id, duration = res[0]
    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"

    caption = (f"🎬 **الحلقة {ep_num}**\n"
               f"⏱ **المدة:** {duration}\n"
               f"✨ **الجودة:** {quality}\n\n"
               f"📥 لمشاهدة الحلقة اضغط على الزر أدناه:")

    try:
        await client.send_photo(
            chat_id=PUBLIC_CHANNEL,
            photo=poster_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ تشغيل الحلقة", url=watch_link)]])
        )
        db_execute("UPDATE videos SET quality=?, status='posted' WHERE v_id=?", (quality, v_id), fetch=False)
        await query.message.edit_text(f"🚀 تم النشر بنجاح في {PUBLIC_CHANNEL}")
    except Exception as e:
        await query.message.edit_text(f"❌ خطأ في النشر: {e}")

# =========================
# 5️⃣ نظام التشغيل
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        try:
            await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        except:
            await message.reply_text("❌ الحلقة غير متوفرة حالياً.")
    else:
        await message.reply_text("أهلاً بك يا محمد! استخدم روابط القناة للمشاهدة.")

app.run()
