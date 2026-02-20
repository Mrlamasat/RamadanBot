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
# تأكد أن PUBLIC_CHANNEL في Railway لا يحتوي على @
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, status TEXT, ep_num INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                      (user_id INTEGER, poster_id TEXT, UNIQUE(user_id, poster_id))''')
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

# --- دالة التحقق من الاشتراك الموحدة ---
async def is_subscribed(client, user_id):
    try:
        chat_id = f"@{PUBLIC_CHANNEL}"
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        logging.error(f"Error checking subscription: {e}")
    return False

# ===== استقبال ونشر الفيديوهات =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    file = message.video or message.document
    duration = getattr(file, "duration", 0)
    db_execute(
        "INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
        (str(message.id), format_duration(duration), "waiting"), fetch=False
    )
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\nأرسل البوستر الآن.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute(
        "UPDATE videos SET title = ?, poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
        (message.caption or "حلقة جديدة", message.photo.file_id, v_id), fetch=False
    )
    await message.reply_text(f"📌 تم استلام البوستر.\n🔢 أرسل الآن رقم الحلقة فقط:")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start", "edit", "list"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
         InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}"),
         InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}")]
    ])
    await message.reply_text(f"✅ رقم الحلقة: {message.text}\nاختر الجودة للنشر في قناة التخزين أولاً:", reply_markup=markup)

@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id, ep_num FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, p_id, ep_num = res[0]
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    caption_text = f"🎬 **الحلقة {ep_num}**\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 [مشاهدة الآن]({link})"
    
    # النشر في قناة التخزين ليتأكد المشرف
    await client.send_photo(CHANNEL_ID, photo=p_id, caption=caption_text, 
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
    
    # إشعار المشتركين
    subscribers = db_execute("SELECT user_id FROM subscriptions WHERE poster_id = ?", (p_id,))
    for sub in subscribers:
        try:
            await client.send_message(sub[0], f"🔔 **تحديث جديد!**\nتم إضافة الحلقة {ep_num} 🎬.\n📥 [اضغط هنا للمشاهدة]({link})")
        except: pass
    await query.message.delete()

# ===== نظام Start المصلح =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت المسلسلات! 🌙")
        return

    v_id = message.command[1]
    
    if await is_subscribed(client, message.from_user.id):
        # المستخدم مشترك -> ارسل الفيديو
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        
        # جلب بيانات المسلسل لعرض باقي الحلقات
        video_data = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if video_data and video_data[0][0]:
            p_id = video_data[0][0]
            # تسجيل المستخدم في التنبيهات تلقائياً عند المشاهدة
            db_execute("INSERT OR IGNORE INTO subscriptions (user_id, poster_id) VALUES (?, ?)", 
                       (message.from_user.id, p_id), fetch=False)
            
            # جلب الحلقات المرتبطة
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC", (p_id,))
            if len(all_ep) > 1:
                btns = []; row = []
                for vid, num in all_ep:
                    row.append(InlineKeyboardButton(f"الحلقة {num}", url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                    if len(row) == 2: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 **باقي حلقات المسلسل:**", reply_markup=InlineKeyboardMarkup(btns))
    else:
        # غير مشترك
        btn = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ **عذراً، يجب عليك الاشتراك في القناة لمشاهدة الحلقة.**", reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub_btn(client, query):
    v_id = query.data.split("_")[1]
    if await is_subscribed(client, query.from_user.id):
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    else:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)

app.run()
