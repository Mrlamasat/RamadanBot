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

# ===== إعداد قاعدة البيانات المتقدمة =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    # جدول الفيديوهات
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, status TEXT, ep_num INTEGER, poster_file_id TEXT, views INTEGER DEFAULT 0)''')
    # جدول المشتركين في التحديثات
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                      (user_id INTEGER, poster_id TEXT, UNIQUE(user_id, poster_id))''')
    # جدول مستخدمي البوت (للإحصائيات)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # تحديث الأعمدة لضمان التوافق
    cursor.execute("PRAGMA table_info(videos)")
    columns = [col[1] for col in cursor.fetchall()]
    if "views" not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN views INTEGER DEFAULT 0")
    if "poster_file_id" not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN poster_file_id TEXT")
    
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

# ===== 1. استقبال الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (str(message.id), format_duration(duration), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\n🖼 أرسل البوستر الآن.")

# ===== 2. استقبال البوستر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, poster_file_id = ?, status = 'awaiting_ep' WHERE v_id = ?", 
               (message.caption or "حلقة جديدة", message.photo.file_unique_id, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم الاستلام للفيديو {v_id}.\n🔢 أرسل رقم الحلقة فقط:")

# ===== 3. استقبال رقم الحلقة =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start", "stats", "fix_old"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"✅ جاهز للنشر (الحلقة {message.text}):", reply_markup=markup)

# ===== 4. معالجة النشر =====
@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id, poster_file_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, p_uid, p_fid = res[0]
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"

    await client.send_photo(CHANNEL_ID, photo=p_fid, 
                           caption=f"🎬 **{title}**\n✨ الجودة: {quality}\n\n📥 [مشاهدة الآن]({link})",
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
    await query.message.delete()
    await query.answer("✅ تم النشر!", show_alert=True)

# ===== 5. نظام الـ Start والإحصائيات =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    # تسجيل المستخدم الجديد في الإحصائيات
    db_execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,), fetch=False)

    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد في بوت المشاهدة الحصري!")
        return

    v_id = message.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        
        # زيادة عداد المشاهدات لهذه الحلقة
        db_execute("UPDATE videos SET views = views + 1 WHERE v_id = ?", (v_id,), fetch=False)
        
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

        video_data = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if video_data and video_data[0][0]:
            p_id = video_data[0][0]
            db_execute("INSERT OR IGNORE INTO subscriptions (user_id, poster_id) VALUES (?, ?)", (message.from_user.id, p_id), fetch=False)
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC", (p_id,))
            if len(all_ep) > 1:
                btns = []; row = []
                for vid, num in all_ep:
                    label = f"•{num}•" if str(vid) == v_id else f"{num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                    if len(row) == 5: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي الحلقات:", reply_markup=InlineKeyboardMarkup(btns))

    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك بالقناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك أولاً لتتمكن من المشاهدة.", reply_markup=InlineKeyboardMarkup(btn))

# ===== 6. أمر الإحصائيات (لمحمد Almohsen فقط) =====
@app.on_message(filters.command("stats") & filters.private)
async def show_stats(client, message):
    # إحصائيات عامة
    total_users = db_execute("SELECT COUNT(*) FROM users")[0][0]
    total_videos = db_execute("SELECT COUNT(*) FROM videos WHERE status = 'posted'")[0][0]
    total_views = db_execute("SELECT SUM(views) FROM videos")[0][0] or 0
    
    # أكثر 5 حلقات مشاهدة
    top_videos = db_execute("SELECT title, ep_num, views FROM videos ORDER BY views DESC LIMIT 5")
    top_text = "\n".join([f"🔥 {v[0]} (حلقة {v[1]}): {v[2]} مشاهدة" for v in top_videos])

    stats_msg = (
        f"📊 **إحصائيات بوت Mohammed Almohsen:**\n\n"
        f"👥 عدد المستخدمين: `{total_users}`\n"
        f"🎬 عدد الحلقات المنشورة: `{total_videos}`\n"
        f"👁 إجمالي المشاهدات: `{total_views}`\n\n"
        f"🔝 **الأكثر مشاهدة:**\n{top_text}"
    )
    await message.reply_text(stats_msg)

@app.on_message(filters.command("fix_old") & filters.private)
async def fix_old(client, message):
    db_execute("UPDATE videos SET status = 'posted' WHERE status IS NOT 'posted'", fetch=False)
    await message.reply_text("✅ تم الإصلاح.")

app.run()
