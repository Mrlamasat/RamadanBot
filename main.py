import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== إعدادات البوت =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0)) 
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")
SECOND_CHANNEL = os.environ.get("SECOND_CHANNEL", "RamadanSeries26").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات المحدثة =====
DB_FILE = "bot_data.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute('''CREATE TABLE IF NOT EXISTS videos 
                        (v_id TEXT PRIMARY KEY, file_unique_id TEXT, duration TEXT, title TEXT, 
                         poster_id TEXT, ep_num INTEGER, status TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"خطأ في إنشاء قاعدة البيانات: {e}")

init_db()

def db_execute(query, params=(), fetch=True):
    res = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10) # أضفنا timeout لمنع التعليق
        cursor = conn.execute(query, params)
        if fetch:
            res = cursor.fetchall()
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"خطأ في تنفيذ الاستعلام: {e}")
    return res

# ===== 1. استقبال الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    file = message.video or message.document
    if message.document and not (message.document.mime_type and message.document.mime_type.startswith("video/")):
        return

    duration_str = "غير معروفة"
    if hasattr(file, 'duration') and file.duration:
        duration_str = f"{file.duration//60}:{file.duration%60:02d} دقيقة"
    
    db_execute(
        "INSERT OR REPLACE INTO videos (v_id, file_unique_id, duration, status) VALUES (?, ?, ?, ?)",
        (str(message.id), file.file_unique_id, duration_str, "waiting"), fetch=False
    )

    await message.reply_text(
        f"✅ **تم استلام الفيديو بنجاح!**\n⏱ المدة: {duration_str}\n\n🖼 **أرسل البوستر الآن (صورة فقط).**"
    )

# ===== 2. استقبال البوستر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res:
        await message.reply_text("❌ ارفع الفيديو أولاً.")
        return

    v_id = res[0][0]
    db_execute("UPDATE videos SET poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?", 
               (message.photo.file_id, v_id), fetch=False)
    
    await message.reply_text("📌 **تم ربط البوستر.**\nأرسل الآن **رقم الحلقة** (أرقام فقط).")

# ===== 3. استقبال الرقم والنشر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id, poster_id, duration FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res: return

    if not message.text.isdigit():
        await message.reply_text("❌ أرسل رقماً فقط.")
        return

    v_id, p_id, duration = res[0]
    ep_num = int(message.text)
    db_execute("UPDATE videos SET ep_num = ?, status = 'posted' WHERE v_id = ?", (ep_num, v_id), fetch=False)

    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"

    caption_text = (f"🎬 **الحلقة {ep_num}**\n⏱ المـدة: {duration}\n✨ الجودة: HD\n\n📥 مشاهدة الآن")

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشـاهدة الآن", url=link)],
        [InlineKeyboardButton("🔥 أعجبتني", callback_data="like"), 
         InlineKeyboardButton("⭐️ 9.5/10", callback_data="rate")]
    ])

    await client.send_photo(f"@{PUBLIC_CHANNEL}", photo=p_id, caption=caption_text, reply_markup=buttons)
    try: await client.send_photo(f"@{SECOND_CHANNEL}", photo=p_id, caption=caption_text, reply_markup=buttons)
    except: pass
    await message.reply_text(f"🚀 **تم النشر بنجاح للحلقة {ep_num}!**")

# ===== 4. نظام Start للمشاهدين =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}! 🌙")
        return
    v_id = message.command[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", message.from_user.id)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        
        # ميزة الأزرار التلقائية
        current = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if current:
            p_id = current[0][0]
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC", (p_id,))
            if len(all_ep) > 1:
                btns = []; row = []
                for vid, num in all_ep:
                    row.append(InlineKeyboardButton(f"الحلقة {num}", url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                    if len(row) == 2: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 **باقي حلقات المسلسل:**", reply_markup=InlineKeyboardMarkup(btns))
    except:
        btn = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex("^(like|rate)$"))
async def interactions(client, query):
    await query.answer("شكراً لتفاعلك! 🔥")

@app.on_callback_query(filters.regex(r"^chk_"))
async def chk_callback(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await query.answer("⚠️ اشترك أولاً!", show_alert=True)

app.run()
