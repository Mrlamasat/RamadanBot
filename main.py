import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# دالة قاعدة البيانات
def db_execute(query, params=(), fetch=True):
    try:
        conn = sqlite3.connect("bot_data.db", timeout=20)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        res = cursor.fetchall() if fetch else None
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

# إنشاء الجداول
db_execute('''CREATE TABLE IF NOT EXISTS videos 
              (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
               poster_id TEXT, status TEXT, ep_num INTEGER)''', fetch=False)

async def is_subscribed(client, user_id):
    try:
        chat = f"@{PUBLIC_CHANNEL}" if not str(PUBLIC_CHANNEL).startswith("-100") else int(PUBLIC_CHANNEL)
        member = await client.get_chat_member(chat, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return True

# --- استقبال الفيديو والبوستر (للمشرف فقط) ---
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    db_execute("INSERT OR REPLACE INTO videos (v_id, status) VALUES (?, ?)", (v_id, "waiting"), fetch=False)
    await message.reply_text(f"✅ استلمت الفيديو.\nأرسل البوستر الآن.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?", (message.photo.file_id, v_id), fetch=False)
    await message.reply_text("🔢 أرسل رقم الحلقة الآن:")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command("start"))
async def receive_ep(client, message):
    if not message.text.isdigit(): return
    res = db_execute("SELECT v_id, poster_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id, p_id = res[0]
    ep_num = int(message.text)
    db_execute("UPDATE videos SET ep_num = ?, status = 'posted' WHERE v_id = ?", (ep_num, v_id), fetch=False)
    
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = f"🎬 **حلقة جديدة رقم: {ep_num}**\n\nمشاهدة عبر الرابط أو بإرسال الرقم {ep_num} للبوت."
    await client.send_photo(f"@{PUBLIC_CHANNEL}", photo=p_id, caption=caption, 
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    await message.reply_text("🚀 تم النشر!")

# --- معالجة الأوامر والبحث (للمستخدمين) ---

@app.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    # إذا كان رابط عميق (فيه ايدي فيديو)
    if len(message.command) > 1:
        v_id = message.command[1]
        if await is_subscribed(client, message.from_user.id):
            await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        else:
            btn = [[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{PUBLIC_CHANNEL}")]]
            await message.reply_text("⚠️ اشترك أولاً لتشغيل الفيديو.", reply_markup=InlineKeyboardMarkup(btn))
    else:
        await message.reply_text(f"أهلاً بك يا محمد! 🌙\nأرسل رقم الحلقة مباشرة لمشاهدتها.")

@app.on_message(filters.private & filters.text & ~filters.command("start"))
async def search_by_num(client, message):
    if message.text.isdigit():
        res = db_execute("SELECT v_id FROM videos WHERE ep_num = ? AND status = 'posted' LIMIT 1", (int(message.text),))
        if res:
            v_id = res[0][0]
            if await is_subscribed(client, message.from_user.id):
                await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
            else:
                btn = [[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{PUBLIC_CHANNEL}")]]
                await message.reply_text("⚠️ اشترك أولاً لتشغيل الفيديو.", reply_markup=InlineKeyboardMarkup(btn))
        else:
            await message.reply_text("❌ هذه الحلقة غير متوفرة حالياً.")

app.run()
