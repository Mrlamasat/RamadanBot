import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))

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

# ===== استقبال المحتوى (قناة التخزين) =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
               (str(message.id), format_duration(duration), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\nأرسل البوستر الآن.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (message.caption or "حلقة جديدة", message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم استلام البوستر.\n🔢 أرسل رقم الحلقة:")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'posted' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    await message.reply_text(f"✅ تم حفظ الحلقة رقم {message.text}\nرابط المشاهدة:\n{link}")

# ===== نظام الـ Start (إرسال مباشر بدون اشتراك إجباري) =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد! أرسل رقم الحلقة للمشاهدة.")
        return

    v_id = message.command[1]
    try:
        # إرسال الفيديو مباشرة
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        
        # عرض حلقات أخرى إذا وجدت
        video_data = db_execute("SELECT poster_id, ep_num FROM videos WHERE v_id = ?", (v_id,))
        if video_data and video_data[0][0]:
            p_id = video_data[0][0]
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? ORDER BY ep_num ASC", (p_id,))
            
            if len(all_ep) > 1:
                btns = []; row = []
                bot_info = await client.get_me()
                for v_id_item, num in all_ep:
                    label = f"▶️ {num}" if v_id_item == v_id else f"{num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id_item}"))
                    if len(row) == 4: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي الحلقات:", reply_markup=InlineKeyboardMarkup(btns))
                
    except Exception as e:
        await message.reply_text("❌ عذراً، هذا الرابط لم يعد يعمل أو تم حذف الفيديو.")

app.run()
