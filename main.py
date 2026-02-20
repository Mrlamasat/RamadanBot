import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# المتغيرات
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# دالة الوقت (موجودة ومفعلة)
def format_duration(seconds):
    if not seconds: return "00:00"
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d} دقيقة"

# قاعدة البيانات
def db_execute(query, params=(), fetch=True):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    res = cursor.fetchall() if fetch else None
    conn.close()
    return res

# 1. استقبال الفيديو وحساب الوقت
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
               (str(message.id), format_duration(duration), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم ربط الفيديو ومدته: {format_duration(duration)}\n🖼 أرسل البوستر الآن.")

# 2. استقبال البوستر
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (message.caption or "حلقة جديدة", message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة:")

# 3. استخدام التنسيق المختصر للأزرار (الذي أرسلته أنت)
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    
    # --- الكود المختصر الذي أرسلته تم دمجه هنا ---
    qualities = ["HD", "SD", "4K"]
    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton(q, callback_data=f"q_{q}_{v_id}") for q in qualities]
    ])
    # ------------------------------------------
    
    await message.reply_text(f"✅ الحلقة {message.text} جاهزة.\nاختر الجودة للنشر:", reply_markup=btns)

# 4. النشر النهائي (يشمل الوقت والجودة)
@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, p_id = res[0]
    
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    
    # النص النهائي يشمل مدة الحلقة التي سألت عنها
    caption = f"🎬 **{title}**\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 [مشاهدة الآن]({link})"
    
    await client.send_photo(os.environ.get("PUBLIC_CHANNEL"), photo=p_id, caption=caption,
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
    await query.message.edit_text("🚀 تم النشر بنجاح!")

app.run()
