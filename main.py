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

# ===== تهيئة قاعدة البيانات وإصلاحها تلقائياً =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, poster_file_id TEXT, ep_num INTEGER, status TEXT)''')
    
    cursor.execute("PRAGMA table_info(videos)")
    columns = [col[1] for col in cursor.fetchall()]
    needed = {"duration": "TEXT", "title": "TEXT", "ep_num": "INTEGER", "poster_file_id": "TEXT"}
    for col, type_col in needed.items():
        if col not in columns:
            cursor.execute(f"ALTER TABLE videos ADD COLUMN {col} {type_col}")
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

# 1. استقبال الفيديو في قناة التخزين
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    db_execute("INSERT OR REPLACE INTO videos (v_id, status) VALUES (?, ?)",
               (str(message.id), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو ({message.id})\nالآن أرسل **البوستر (الصورة)** فقط.")

# 2. استقبال البوستر (يطلب بعدها رقم الحلقة)
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    
    db_execute("UPDATE videos SET poster_id = ?, poster_file_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (message.photo.file_id, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم ربط البوستر.\nالآن أرسل **رقم الحلقة** (أرقام فقط):")

# 3. استقبال رقم الحلقة والنشر الفوري
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id, poster_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    
    v_id, p_id = res[0]
    ep_num = int(message.text)
    
    # تحديث البيانات وتغيير الحالة لمنشور (Posted)
    db_execute("UPDATE videos SET ep_num = ?, status = 'posted' WHERE v_id = ?", (ep_num, v_id), fetch=False)
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    # تنسيق الرسالة للنشر في القناة العامة
    caption_text = (f"🎬 **حلقة جديدة جاهزة**\n"
                    f"🔢 رقم الحلقة: {ep_num}\n\n"
                    f"📥 [مشاهدة الآن من هنا]({link})")
    
    await client.send_photo(f"@{PUBLIC_CHANNEL}", photo=p_id, caption=caption_text,
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    await message.reply_text(f"✅ تم حفظ الحلقة {ep_num} ونشرها في القناة العامة بنجاح!")

# 4. نظام الـ Start للمشاهدين (يدعم الترقيم الذكي للقديم)
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت المسلسلات! 🌙")
        return
    v_id = message.command[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", message.from_user.id)
        
        # إرسال الفيديو (محمي)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        
        # عرض قائمة الحلقات (ترقيم تلقائي للبيانات القديمة)
        video_data = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if video_data and video_data[0][0]:
            p_id = video_data[0][0]
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY rowid ASC", (p_id,))
            
            if len(all_ep) > 1:
                btns = []; row = []
                for i, (v_id_item, num) in enumerate(all_ep, 1):
                    # الترقيم الذكي: إذا كان num هو None استخدم i
                    display_num = num if (num is not None and num != "") else i
                    label = f"الحلقة {display_num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={v_id_item}"))
                    if len(row) == 2: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي حلقات المسلسل:", reply_markup=InlineKeyboardMarkup(btns))
                
    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=InlineKeyboardMarkup(btn))

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
