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

# ===== استقبال الفيديو والبوستر =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (str(message.id), format_duration(duration), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\n🖼 أرسل البوستر الآن كصورة.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, poster_file_id = ?, status = 'awaiting_ep' WHERE v_id = ?", 
               (message.caption or "حلقة جديدة", message.photo.file_unique_id, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 استلمت البوستر لـ {v_id}.\n🔢 أرسل رقم الحلقة فقط:")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start","stats","edit","fix_old","fix_old_data"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
                                    InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"✅ جاهز للنشر (حلقة {message.text}):", reply_markup=markup)

# ===== نشر الفيديو مع البوستر الأصلي =====
@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id, poster_file_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, poster_uid, poster_fid = res[0]
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"

    # إرسال الصورة الأصلية بدون زر التشغيل GIF
    await client.send_photo(CHANNEL_ID, photo=poster_fid, 
                           caption=f"🎬 **{title}**\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 [مشاهدة الآن]({link})",
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)

    # إشعارات المشتركين
    subscribers = db_execute("SELECT user_id FROM subscriptions WHERE poster_id = ?", (poster_uid,))
    for sub in subscribers:
        try:
            await client.send_message(sub[0], f"🔔 **حلقة جديدة!**\nتم إضافة حلقة من: {title}\n📥 [شاهدها من هنا]({link})")
            await asyncio.sleep(0.05)
        except: pass
    
    await query.message.delete()
    await query.answer("✅ تم النشر!", show_alert=True)

# ===== معالجة الحلقات القديمة (ربطها بالبوسترات) =====
@app.on_message(filters.command("fix_old_data") & filters.private)
async def fix_old_data(client, message):
    msg_wait = await message.reply_text("⏳ جاري فحص القناة وربط الحلقات بالبوسترات...")
    count = 0
    async for msg in client.get_chat_history(CHANNEL_ID, limit=None):
        v_id = str(msg.id)
        if msg.video or (msg.document and "video" in msg.document.mime_type):
            duration = format_duration(msg.video.duration if msg.video else getattr(msg.document, "duration", 0))
            db_execute("INSERT OR IGNORE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
                       (v_id, duration, "posted"), fetch=False)
            count += 1
            if msg.reply_to_message and msg.reply_to_message.photo:
                p = msg.reply_to_message.photo
                db_execute("UPDATE videos SET poster_id=?, poster_file_id=?, title=? WHERE v_id=?",
                           (p.file_unique_id, p.file_id, msg.caption or "حلقة قديمة", v_id), fetch=False)
        elif msg.photo and msg.caption and "start=" in msg.caption:
            try:
                extracted_v_id = msg.caption.split("start=")[1].split()[0]
                db_execute("UPDATE videos SET poster_id=?, poster_file_id=?, status='posted' WHERE v_id=?",
                           (msg.photo.file_unique_id, msg.photo.file_id, extracted_v_id), fetch=False)
            except: pass
    await msg_wait.edit(f"✅ تم معالجة {count} فيديو قديم وربطه بالبوسترات!")

# ===== نظام Start يعتمد على poster_id فقط =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    db_execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,), fetch=False)
    
    if len(message.command) <= 1:
        await message.reply_text("أهلاً بك في بوت المشاهدة! 🎬")
        return

    v_id = message.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        db_execute("UPDATE videos SET views = views + 1 WHERE v_id = ?", (v_id,), fetch=False)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

        # ربط المستخدم بالبوستر
        res = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if not res or not res[0][0]:
            return
        poster_id = res[0][0]
        db_execute("INSERT OR IGNORE INTO subscriptions (user_id, poster_id) VALUES (?, ?)", 
                   (message.from_user.id, poster_id), fetch=False)

        # عرض كل الحلقات المرتبطة بالبوستر
        all_eps = db_execute(
            "SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC, v_id ASC",
            (poster_id,)
        )
        if all_eps:
            btns, row = [], []
            for vid, num in all_eps:
                label = f"▶️ {num}" if str(vid) == v_id else f"{num if num else '?'}"
                row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                if len(row) == 5:
                    btns.append(row)
                    row = []
            if row: btns.append(row)
            await message.reply_text("📺 حلقات هذا المسلسل:", reply_markup=InlineKeyboardMarkup(btns))

    except UserNotParticipant:
        btn = [
            [InlineKeyboardButton("📢 اشترك بالقناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
            [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]
        ]
        await message.reply_text("⚠️ اشترك أولاً لتتمكن من المشاهدة.", reply_markup=InlineKeyboardMarkup(btn))

# ===== أوامر التحكم والإحصائيات =====
@app.on_message(filters.command("stats") & filters.private)
async def show_stats(client, message):
    total_u = db_execute("SELECT COUNT(*) FROM users")[0][0]
    total_v = db_execute("SELECT SUM(views) FROM videos")[0][0] or 0
    top_5 = db_execute("SELECT title, ep_num, views FROM videos ORDER BY views DESC LIMIT 5")
    top_text = "\n".join([f"🔥 {v[0]} ({v[1]}): {v[2]} مشاهدة" for v in top_5])
    await message.reply_text(f"📊 **إحصائيات Mohammed Almohsen:**\n\n👥 مستخدمين: `{total_u}`\n👁 مشاهدات: `{total_v}`\n\n🔝 الأكثر طلباً:\n{top_text}")

@app.on_message(filters.command("edit") & filters.private)
async def edit_title(client, message):
    if len(message.command) < 3: return
    if message.command[1].lower() == "all":
        res = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (message.command[2],))
        if res:
            db_execute("UPDATE videos SET title = ? WHERE poster_id = ?", (" ".join(message.command[3:]), res[0][0]), fetch=False)
            await message.reply_text("✅ تم تعديل اسم المسلسل بالكامل.")
    else:
        db_execute("UPDATE videos SET title = ? WHERE v_id = ?", (" ".join(message.command[2:]), message.command[1]), fetch=False)
        await message.reply_text("✅ تم تعديل العنوان.")

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
