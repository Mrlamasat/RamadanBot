import os
import sqlite3
import logging
import asyncio
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
DB_PATH = os.environ.get("DB_PATH", "bot_data.db") 

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, status TEXT, ep_num INTEGER)''')
    # جدول المشتركين للإشعارات
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                      (user_id INTEGER, poster_id TEXT, UNIQUE(user_id, poster_id))''')
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=True):
    conn = sqlite3.connect(DB_PATH)
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
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\nالآن أرسل البوستر (الصورة).")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    # سنعتمد "حلقة جديدة" كعنوان افتراضي بناءً على طلبك
    title = "حلقة جديدة" 
    db_execute("UPDATE videos SET title = ?, poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (title, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"🖼 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة فقط:")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    if not message.text.isdigit(): return
    res = db_execute("SELECT v_id, title, poster_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    
    v_id, title, poster_id = res[0]
    ep_num = int(message.text)
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (ep_num, v_id), fetch=False)
    
    # إضافة أزرار الجودة قبل النشر النهائي
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}"),
         InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
         InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}")]
    ])
    await message.reply_text(f"✅ الحلقة {ep_num} جاهزة.\nاختر الجودة للنشر في @{PUBLIC_CHANNEL}:", reply_markup=markup)

# ===== معالجة النشر والإشعارات =====

@app.on_callback_query(filters.regex(r"^q_"))
async def publish_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT ep_num, poster_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    ep_num, poster_id = res[0]
    
    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    # 1. النشر في القناة العامة
    try:
        caption = f"🎬 **حلقة جديدة جاهزة**\n🔹 **رقم الحلقة:** {ep_num}\n✨ **الجودة:** {quality}\n\n📥 **لمشاهدة الحلقة اضغط هنا:**"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        await client.send_photo(chat_id=f"@{PUBLIC_CHANNEL}", photo=poster_id, caption=caption, reply_markup=markup)
        await query.message.edit_text(f"🚀 تم النشر بنجاح بجودة {quality}")
    except Exception as e:
        await query.message.edit_text(f"⚠️ فشل النشر في القناة: {e}")

    # 2. إرسال إشعارات للمشتركين (اختياري)
    subs = db_execute("SELECT user_id FROM subscriptions WHERE poster_id = ?", (poster_id,))
    for sub in subs:
        try:
            await client.send_message(sub[0], f"🔔 تحديث: تم إضافة الحلقة {ep_num} جودة {quality}!\n[شاهد من هنا]({watch_link})")
            await asyncio.sleep(0.1)
        except: continue
        
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)

# ===== نظام التشغيل (Start) =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد! أرسل رابط الحلقة للمشاهدة.")
        return

    v_id = message.command[1]
    
    # التحقق من الاشتراك الإجباري
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", message.from_user.id)
    except UserNotParticipant:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
            [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]
        ])
        await message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً لمشاهدة الحلقة.", reply_markup=markup)
        return

    await send_video(client, message.chat.id, v_id)

async def send_video(client, chat_id, v_id):
    try:
        await client.copy_message(chat_id, CHANNEL_ID, int(v_id), protect_content=True)
        video_info = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if video_info and video_info[0][0]:
            p_id = video_info[0][0]
            # حفظ اشتراك المستخدم في هذا المسلسل للإشعارات
            db_execute("INSERT OR IGNORE INTO subscriptions (user_id, poster_id) VALUES (?, ?)", (chat_id, p_id), fetch=False)
            
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC", (p_id,))
            if len(all_ep) > 1:
                btns = []; row = []
                bot_user = (await client.get_me()).username
                for vid, num in all_ep:
                    label = f"▶️ {num}" if vid == v_id else f"{num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_user}?start={vid}"))
                    if len(row) == 4: btns.append(row); row = []
                if row: btns.append(row)
                await client.send_message(chat_id, "📺 باقي حلقات المسلسل:", reply_markup=InlineKeyboardMarkup(btns))
    except:
        await client.send_message(chat_id, "❌ الحلقة غير متوفرة.")

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", query.from_user.id)
        await query.message.delete()
        await send_video(client, query.from_user.id, v_id)
    except:
        await query.answer("⚠️ اشترك أولاً!", show_alert=True)

app.run()
