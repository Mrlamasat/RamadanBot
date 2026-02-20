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

# ===== إعداد قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, status TEXT, ep_num INTEGER, poster_file_id TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                      (user_id INTEGER, poster_id TEXT, UNIQUE(user_id, poster_id))''')
    
    cursor.execute("PRAGMA table_info(videos)")
    columns = [col[1] for col in cursor.fetchall()]
    if "ep_num" not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN ep_num INTEGER")
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
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\n🖼 أرسل البوستر الآن كصورة.")

# ===== 2. استقبال البوستر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res:
        await message.reply_text("⚠️ ارفع فيديو أولاً.")
        return
        
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, poster_file_id = ?, status = 'awaiting_ep' WHERE v_id = ?", 
               (message.caption or "حلقة جديدة", message.photo.file_unique_id, message.photo.file_id, v_id), fetch=False)
    
    await message.reply_text(f"📌 تم استلام البوستر للفيديو {v_id}.\n🔢 **أرسل الآن رقم الحلقة فقط:**")

# ===== 3. استقبال رقم الحلقة =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start", "edit"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
        InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}"),
        InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}")
    ]])
    await message.reply_text(f"✅ رقم الحلقة: {message.text}\nاختر الجودة للنشر:", reply_markup=markup)

# ===== 4. معالجة النشر (البحث في آخر 50 رسالة) =====
@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id, poster_file_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, p_uid, p_fid = res[0]
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"

    # محاولة جلب الصورة: الأولوية لـ file_id المخزن، ثم البحث في التاريخ
    photo_to_send = p_fid 
    
    # إذا لم نجد المعرف أو أردنا التأكد، نبحث في آخر 50 رسالة في تاريخ القناة
    if not photo_to_send or photo_to_send.startswith("AgAC"): # AgAC هو بادئة للـ unique_id أحياناً
        async for msg in client.get_chat_history(CHANNEL_ID, limit=50):
            if msg.photo and msg.photo.file_unique_id == p_uid:
                photo_to_send = msg.photo.file_id
                break

    if not photo_to_send:
        await query.answer("❌ تعذر العثور على ملف البوستر في آخر 50 رسالة!", show_alert=True)
        return

    try:
        await client.send_photo(CHANNEL_ID, photo=photo_to_send, 
                               caption=f"🎬 **{title}**\n⏱ المـدة: {duration}\n✨ الجـودة: {quality}\n\n📥 [مشاهدة الآن]({link})",
                               reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
        
        db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
        
        # إرسال إشعارات للمشتركين
        subscribers = db_execute("SELECT user_id FROM subscriptions WHERE poster_id = ?", (p_uid,))
        for sub in subscribers:
            try:
                await client.send_message(sub[0], f"🔔 **تحديث جديد!**\n\nتم إضافة حلقة جديدة في المسلسل الذي تتابعه.\n📥 [اضغط للمشاهدة]({link})", disable_web_page_preview=True)
            except: pass
        
        await query.message.delete()
        await query.answer("✅ تم النشر بنجاح!", show_alert=True)
    except Exception as e:
        logging.error(f"Error during posting: {e}")
        await query.answer(f"❌ خطأ أثناء النشر: {e}", show_alert=True)

# ===== 5. Start Handler =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد!")
        return

    v_id = message.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        channel_msg = await client.get_messages(CHANNEL_ID, int(v_id))
        video_data = db_execute("SELECT poster_id, title, ep_num FROM videos WHERE v_id = ?", (v_id,))

        # نظام الإنقاذ للربط التلقائي
        if not video_data or not video_data[0][0]:
            p_id = channel_msg.reply_to_message.photo.file_unique_id if channel_msg.reply_to_message and channel_msg.reply_to_message.photo else None
            duration = format_duration(channel_msg.video.duration) if channel_msg.video else "00:00"
            db_execute("INSERT OR REPLACE INTO videos (v_id, duration, title, poster_id, status) VALUES (?, ?, ?, ?, ?)", 
                       (v_id, duration, "حلقة", p_id, "posted"), fetch=False)
            video_data = db_execute("SELECT poster_id, title, ep_num FROM videos WHERE v_id = ?", (v_id,))

        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

        if video_data and video_data[0][0]:
            p_id = video_data[0][0]
            db_execute("INSERT OR IGNORE INTO subscriptions (user_id, poster_id) VALUES (?, ?)", (message.from_user.id, p_id), fetch=False)
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY COALESCE(ep_num, 999) ASC, rowid ASC", (p_id,))
            if len(all_ep) > 1:
                btns = []; row = []
                bot_info = await client.get_me()
                for i, (v_id_item, num) in enumerate(all_ep, 1):
                    display_num = num if num else i
                    label = f"▶️ {display_num}" if v_id_item == v_id else f"{display_num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id_item}"))
                    if len(row) == 4: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 حلقات المسلسل:", reply_markup=InlineKeyboardMarkup(btns))

    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك بالقناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك بالقناة لتفعيل الرابط.", reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)

app.run()
