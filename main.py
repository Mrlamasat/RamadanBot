import os
import sqlite3
import logging
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية (من Railway) =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== تهيئة قاعدة البيانات وإصلاحها =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, poster_file_id TEXT, ep_num INTEGER, status TEXT)''')
    
    # فحص وإضافة الأعمدة الناقصة لضمان التوافق مع البيانات القديمة
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

# 1. استقبال الفيديو الجديد
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    db_execute("INSERT OR REPLACE INTO videos (v_id, status) VALUES (?, ?)",
               (str(message.id), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو ({message.id})\nالآن أرسل البوستر واكتب رقم الحلقة في الوصف.")

# 2. استقبال البوستر والربط (النظام الذكي)
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    
    # محاولة استخراج الرقم من الوصف
    caption = message.caption or ""
    ep_match = re.search(r'\d+', caption)
    ep_num = int(ep_match.group()) if ep_match else None
    
    db_execute("UPDATE videos SET poster_id = ?, poster_file_id = ?, ep_num = ?, status = 'posted' WHERE v_id = ?",
               (message.photo.file_id, message.photo.file_id, ep_num, v_id), fetch=False)
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    msg_pub = f"🎬 **تم إضافة حلقة جديدة**\n"
    if ep_num: msg_pub += f"🔢 رقم الحلقة: {ep_num}\n"
    msg_pub += f"\n📥 [مشاهدة الآن من هنا]({link})"
    
    await client.send_photo(f"@{PUBLIC_CHANNEL}", photo=message.photo.file_id, caption=msg_pub,
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    await message.reply_text(f"✅ تم الربط والنشر بنجاح!")

# 3. نظام التشغيل (Start) وحل مشكلة None للبيانات القديمة
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}!")
        return
    
    v_id = message.command[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", message.from_user.id)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        
        # جلب البوستر للحلقة الحالية
        video_info = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if video_info and video_info[0][0]:
            p_id = video_info[0][0]
            # جلب كل الحلقات التي لها نفس البوستر
            # الترتيب هنا يعتمد على صف rowid لضمان التسلسل الصحيح للبيانات القديمة
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY rowid ASC", (p_id,))
            
            if len(all_ep) > 1:
                btns = []; row = []
                for i, (v_id_item, num) in enumerate(all_ep, 1):
                    # الترقيم الذكي: إذا لم يوجد رقم (None)، استخدم ترتيبه في القائمة (i)
                    final_num = num if num is not None else i
                    label = f"الحلقة {final_num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={v_id_item}"))
                    if len(row) == 2: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي حلقات المسلسل:", reply_markup=InlineKeyboardMarkup(btns))
                
    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ يجب الاشتراك أولاً لمشاهدة الحلقة.", reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex(r"^chk_"))
async def chk_callback(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)

app.run()
