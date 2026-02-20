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

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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

# ===== استقبال الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (str(message.id), format_duration(duration), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\n🖼 أرسل البوستر الآن.")

# ===== استقبال البوستر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, poster_file_id = ?, status = 'awaiting_ep' WHERE v_id = ?", 
               (message.caption or "حلقة جديدة", message.photo.file_unique_id, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم الاستلام للفيديو {v_id}.\n🔢 أرسل رقم الحلقة فقط:")

# ===== استقبال رقم الحلقة =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
                                    InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"✅ جاهز للنشر (الحلقة {message.text}):", reply_markup=markup)

# ===== النشر بدون أي GIF =====
@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id, poster_file_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, poster_uid, poster_fid = res[0]
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"

    # إرسال الصورة الأصلية بجودة كاملة
    await client.send_photo(CHANNEL_ID, photo=poster_fid, 
                           caption=f"🎬 **{title}**\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 [مشاهدة الآن]({link})",
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)

    # إشعارات المشتركين
    subscribers = db_execute("SELECT user_id FROM subscriptions WHERE poster_id = ?", (poster_uid,))
    for sub in subscribers:
        try:
            await client.send_message(sub[0], f"🔔 **تحديث جديد!**\nتم إضافة حلقة جديدة 🎬.\n📥 [اضغط هنا للمشاهدة]({link})", disable_web_page_preview=True)
        except: pass
    
    await query.message.delete()
    await query.answer("✅ تم النشر بنجاح!", show_alert=True)

# ===== نظام الـ Start =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    db_execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,), fetch=False)
    
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك في بوت المشاهدة الحصري!")
        return

    v_id = message.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        channel_msg = await client.get_messages(CHANNEL_ID, int(v_id))
        
        # تسجيل الفيديوهات القديمة إذا لم تكن موجودة
        video_data = db_execute("SELECT poster_id, title, ep_num FROM videos WHERE v_id = ?", (v_id,))
        if not video_data or not video_data[0][0]:
            poster_id = None
            if channel_msg.reply_to_message and channel_msg.reply_to_message.photo:
                poster_id = channel_msg.reply_to_message.photo.file_unique_id
            duration = format_duration(channel_msg.video.duration) if channel_msg.video else "00:00"
            db_execute("INSERT OR REPLACE INTO videos (v_id, duration, title, poster_id, status) VALUES (?, ?, ?, ?, ?)",
                       (v_id, duration, "حلقة قديمة", poster_id, "posted"), fetch=False)
            video_data = db_execute("SELECT poster_id, title, ep_num FROM videos WHERE v_id = ?", (v_id,))

        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

        if video_data and video_data[0][0]:
            poster_id = video_data[0][0]
            db_execute("INSERT OR IGNORE INTO subscriptions (user_id, poster_id) VALUES (?, ?)", (message.from_user.id, poster_id), fetch=False)
            
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC", (poster_id,))
            if len(all_ep) > 1:
                btns, row = [], []
                for vid, num in all_ep:
                    label = f"•{num}•" if str(vid) == v_id else f"{num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                    if len(row) == 5:
                        btns.append(row)
                        row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي الحلقات:", reply_markup=InlineKeyboardMarkup(btns))

    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك بالقناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك أولاً لتتمكن من المشاهدة.", reply_markup=InlineKeyboardMarkup(btn))

# ===== أمر تعديل العنوان =====
@app.on_message(filters.command("edit") & filters.private)
async def edit_title(client, message):
    if len(message.command) < 3: return
    if message.command[1].lower() == "all":
        res = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (message.command[2],))
        if res:
            db_execute("UPDATE videos SET title = ? WHERE poster_id = ?", (" ".join(message.command[3:]), res[0][0]), fetch=False)
            await message.reply_text("✅ تم تحديث اسم المسلسل لجميع الحلقات.")
    else:
        db_execute("UPDATE videos SET title = ? WHERE v_id = ?", (" ".join(message.command[2:]), message.command[1]), fetch=False)
        await message.reply_text("✅ تم تحديث العنوان.")

# ===== التحقق من الاشتراك =====
@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await query.answer("⚠️ اشترك أولاً!", show_alert=True)

app.run()
