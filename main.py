import os
import sqlite3
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", ""))
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

# ==== ملاحظة مهمة: هذا Userbot وليس بوت ====
app = Client("user_session", api_id=API_ID, api_hash=API_HASH)

# ===== قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, poster_file_id TEXT, status TEXT, ep_num INTEGER, views INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                      (user_id INTEGER, poster_id TEXT, UNIQUE(user_id, poster_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
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

def format_duration(seconds):
    if not seconds: return "00:00"
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d} دقيقة"

# ===== استلام الفيديو والبوستر =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (str(message.id), format_duration(duration), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\n🖼 أرسل البوستر الأصلي الآن.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, poster_file_id = ?, status = 'awaiting_ep' WHERE v_id = ?", 
               (message.caption or "حلقة جديدة", message.photo.file_unique_id, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 استلمت البوستر لـ {v_id}.\n🔢 أرسل رقم الحلقة:")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start","stats","edit","fix_old_data"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
                                    InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"✅ جاهز للنشر (حلقة {message.text}):", reply_markup=markup)

@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id, poster_file_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, poster_uid, poster_fid = res[0]
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"

    await client.send_photo(CHANNEL_ID, photo=poster_fid, 
                           caption=f"🎬 **{title}**\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 [مشاهدة الآن]({link})",
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
    await query.message.delete()
    await query.answer("✅ تم النشر!", show_alert=True)

# ===== إصلاح جميع الحلقات القديمة وربطها بالبوستر الأصلي =====
@app.on_message(filters.command("fix_old_data") & filters.private)
async def fix_old_data(client, message):
    msg_wait = await message.reply_text("⏳ جاري سحب الحلقات وربط البوسترات الأصلية (بحث 50 رسالة للخلف)...")
    count_linked = 0
    count_videos = 0
    try:
        async for msg in client.get_chat_history(CHANNEL_ID, limit=None):
            if msg.video or (msg.document and "video" in (msg.document.mime_type or "")):
                v_id = str(msg.id)
                duration = format_duration(msg.video.duration if msg.video else getattr(msg.document, "duration", 0))
                db_execute("INSERT OR IGNORE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
                           (v_id, duration, "posted"), fetch=False)
                count_videos += 1

                # البحث عن أقرب بوستر أصلي قبل الفيديو
                async for search_msg in client.get_chat_history(CHANNEL_ID, offset_id=msg.id, limit=50):
                    if search_msg.photo and not getattr(search_msg.photo, "animation", False):
                        db_execute(
                            "UPDATE videos SET poster_id=?, poster_file_id=?, status='posted' WHERE v_id=?",
                            (search_msg.photo.file_unique_id, search_msg.photo.file_id, v_id), fetch=False
                        )
                        count_linked += 1
                        break

                if count_videos % 10 == 0:
                    try: await msg_wait.edit(f"⏳ جاري الربط...\n🎬 فيديوهات: {count_videos}\n🖼 بوسترات مربوطة: {count_linked}")
                    except: pass

        await msg_wait.edit(f"🏁 اكتمل الربط!\n🎬 فيديوهات: `{count_videos}`\n🖼 بوسترات أصلية مربوطة: `{count_linked}`")
    except Exception as e:
        await msg_wait.edit(f"❌ خطأ أثناء المعالجة: `{e}`")

# ===== نظام Start (الحلقات + تمييز ▶️) =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    db_execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,), fetch=False)
    
    if len(message.command) <= 1:
        await message.reply_text("أهلاً بك في بوت المشاهدة!")
        return

    v_id = message.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        db_execute("UPDATE videos SET views = views + 1 WHERE v_id = ?", (v_id,), fetch=False)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

        res = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if res and res[0][0]:
            p_id = res[0][0]
            db_execute("INSERT OR IGNORE INTO subscriptions (user_id, poster_id) VALUES (?, ?)", (message.from_user.id, p_id), fetch=False)
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC", (p_id,))
            if len(all_ep) > 1:
                btns, row = [], []
                for vid, num in all_ep:
                    label = f"▶️ {num}" if str(vid) == v_id else f"{num if num else '?'}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                    if len(row) == 5: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 حلقات المسلسل المتوفرة:", reply_markup=InlineKeyboardMarkup(btns))
    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك بالقناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك أولاً.", reply_markup=InlineKeyboardMarkup(btn))

app.run()
