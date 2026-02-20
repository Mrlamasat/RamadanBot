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

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, title TEXT, 
                       poster_id TEXT, status TEXT, ep_num INTEGER)''')
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

# ===== استقبال المحتوى من قناة التخزين =====

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    db_execute("INSERT OR REPLACE INTO videos (v_id, status) VALUES (?, ?)", (v_id, "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\nالآن أرسل البوستر (الصورة) فقط.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"🖼 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة فقط:")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    if not message.text.isdigit(): return
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    
    v_id = res[0][0]
    ep_num = int(message.text)
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready' WHERE v_id = ?", (ep_num, v_id), fetch=False)
    
    # عرض أزرار الجودة للنشر
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("SD", callback_data=f"p_SD_{v_id}"),
         InlineKeyboardButton("HD", callback_data=f"p_HD_{v_id}"),
         InlineKeyboardButton("4K", callback_data=f"p_4K_{v_id}")]
    ])
    await message.reply_text(f"✅ الحلقة {ep_num} جاهزة.\nاختر الجودة للنشر في القناة:", reply_markup=markup)

# ===== معالجة زر النشر =====

@app.on_callback_query(filters.regex(r"^p_"))
async def publish_now(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT ep_num, poster_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    ep_num, p_id = res[0]
    
    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    caption = f"🎬 **حلقة جديدة جاهزة**\n🔹 **رقم الحلقة:** {ep_num}\n✨ **الجودة:** {quality}\n\n📥 **لمشاهدة الحلقة اضغط هنا:**"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
    
    try:
        await client.send_photo(chat_id=f"@{PUBLIC_CHANNEL}", photo=p_id, caption=caption, reply_markup=markup)
        db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
        await query.message.edit_text(f"🚀 تم النشر بنجاح بجودة {quality}")
    except Exception as e:
        await query.message.edit_text(f"❌ خطأ في النشر: {e}")

# ===== نظام Start والاشتراك الإجباري =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text("أهلاً بك يا محمد في البوت!")
        return

    v_id = message.command[1]
    
    # تحقق من الاشتراك
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", message.from_user.id)
    except UserNotParticipant:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{PUBLIC_CHANNEL}")],
            [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]
        ])
        await message.reply_text("⚠️ يجب أن تشترك في القناة أولاً للمشاهدة.", reply_markup=markup)
        return

    await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_again(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)

app.run()
