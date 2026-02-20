import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)

# المتغيرات
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# اتصال قاعدة البيانات (محسن للسرعة)
db_conn = sqlite3.connect("bot_data.db", check_same_thread=False)
db_conn.row_factory = sqlite3.Row # لجعل النتائج أسهل في القراءة

def init_db():
    cursor = db_conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, status TEXT, ep_num INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                      (user_id INTEGER, poster_id TEXT, UNIQUE(user_id, poster_id))''')
    db_conn.commit()

init_db()

# دالة التحقق من الاشتراك (سريعة)
async def is_subscribed(client, user_id):
    try:
        chat_target = f"@{PUBLIC_CHANNEL}" if not str(PUBLIC_CHANNEL).startswith("-100") else int(PUBLIC_CHANNEL)
        member = await client.get_chat_member(chat_target, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return True # السماح بالمرور في حال وجود بطء في تليجرام

# استقبال الفيديو
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    file = message.video or message.document
    if message.document and not (message.document.mime_type and message.document.mime_type.startswith("video/")):
        return
    
    duration = getattr(file, "duration", 0)
    mins, secs = divmod(duration, 60)
    d_str = f"{mins}:{secs:02d}"

    cursor = db_conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
                   (str(message.id), d_str, "waiting"))
    db_conn.commit()
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر.")

# استقبال البوستر
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    cursor = db_conn.cursor()
    cursor.execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    res = cursor.fetchone()
    if not res: return

    cursor.execute("UPDATE videos SET poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
                   (message.photo.file_id, res['v_id']))
    db_conn.commit()
    await message.reply_text("🔢 أرسل رقم الحلقة فقط:")

# استقبال الرقم والنشر
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    if not message.text.isdigit(): return
    cursor = db_conn.cursor()
    cursor.execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    res = cursor.fetchone()
    if not res: return

    v_id = res['v_id']
    cursor.execute("UPDATE videos SET ep_num = ?, status = 'posted' WHERE v_id = ?", (int(message.text), v_id))
    db_conn.commit()

    # جلب البيانات للنشر
    cursor.execute("SELECT * FROM videos WHERE v_id = ?", (v_id,))
    data = cursor.fetchone()
    
    bot = await client.get_me()
    link = f"https://t.me/{bot.username}?start={v_id}"
    caption = f"🎬 **الحلقة {message.text}**\n⏱ المدة: {data['duration']}\n\n📥 [مشاهدة الآن]({link})"
    
    await client.send_photo(CHANNEL_ID, photo=data['poster_id'], caption=caption, 
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    await message.reply_text("🚀 تم النشر!")

# نظام Start (الأكثر سرعة)
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text("أهلاً بك! 🌙")
        return

    v_id = message.command[1]
    if await is_subscribed(client, message.from_user.id):
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        
        # جلب باقي الحلقات بسرعة
        cursor = db_conn.cursor()
        cursor.execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        vid_data = cursor.fetchone()
        
        if vid_data and vid_data['poster_id']:
            cursor.execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC", (vid_data['poster_id'],))
            all_eps = cursor.fetchall()
            if len(all_eps) > 1:
                btns = []
                row = []
                bot = await client.get_me()
                for ep in all_eps:
                    row.append(InlineKeyboardButton(f"الحلقة {ep['ep_num']}", url=f"https://t.me/{bot.username}?start={ep['v_id']}"))
                    if len(row) == 2: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي الحلقات:", reply_markup=InlineKeyboardMarkup(btns))
    else:
        btn = [[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك لتشاهد.", reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex(r"^chk_"))
async def chk_callback(client, query):
    v_id = query.data.split("_")[1]
    if await is_subscribed(client, query.from_user.id):
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    else:
        await query.answer("لم تشترك بعد!", show_alert=True)

app.run()
