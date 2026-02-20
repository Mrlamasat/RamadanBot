import os
import sqlite3
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait, PeerIdInvalid

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, poster_file_id TEXT, status TEXT, ep_num INTEGER, views INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                      (user_id INTEGER, poster_id TEXT, UNIQUE(user_id, poster_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
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

# ===== استقبال الفيديوهات والبوسترات الجديدة =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (str(message.id), format_duration(duration), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم ربط الفيديو {message.id}\n🖼 أرسل البوستر الأصلي.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title=?, poster_id=?, poster_file_id=?, status='awaiting_ep' WHERE v_id=?",
               (message.caption or "حلقة جديدة", message.photo.file_unique_id, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم الربط بـ {v_id}.\n🔢 أرسل رقم الحلقة:")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start","stats","edit","fix_old_data"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status='awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num=?, status='ready_quality' WHERE v_id=?", (int(message.text), v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
                                    InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"✅ جاهز للنشر (حلقة {message.text}):", reply_markup=markup)

@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id, poster_file_id FROM videos WHERE v_id=?", (v_id,))
    if not res: return
    duration, title, poster_uid, poster_fid = res[0]
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"

    await client.send_photo(CHANNEL_ID, photo=poster_fid,
                           caption=f"🎬 **{title}**\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 [مشاهدة الآن]({link})",
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status='posted' WHERE v_id=?", (v_id,), fetch=False)
    await query.message.delete()
    await query.answer("✅ تم النشر!", show_alert=True)

# ===== أمر الإصلاح (النسخة المصححة بدون خطأ 'value') =====
@app.on_message(filters.command("fix_old_data") & filters.private)
async def fix_old_data(client, message):
    msg_wait = await message.reply_text("🚀 جاري بدء الفحص الذكي وتجاوز قيود تليجرام...")
    count_linked, count_videos = 0, 0
    
    try:
        # محاولة تنشيط القناة أولاً
        await client.get_chat(CHANNEL_ID)

        async for vid_msg in client.search_messages(CHANNEL_ID, filter="video"):
            try:
                v_id = str(vid_msg.id)
                db_execute("INSERT OR IGNORE INTO videos (v_id, status) VALUES (?, ?)", (v_id, "posted"), fetch=False)
                count_videos += 1

                async for search_msg in client.get_chat_history(CHANNEL_ID, limit=50, offset_id=vid_msg.id):
                    if search_msg.photo and not getattr(search_msg.photo, "animation", False):
                        p = search_msg.photo
                        db_execute("UPDATE videos SET poster_id=?, poster_file_id=?, status='posted' WHERE v_id=?",
                                   (p.file_unique_id, p.file_id, v_id), fetch=False)
                        count_linked += 1
                        break
                
                if count_videos % 20 == 0:
                    try: await msg_wait.edit(f"⏳ جاري الربط...\n🎬 تم العثور على {count_videos} فيديو\n🖼 تم ربط {count_linked} بوستر")
                    except: pass
            
            except FloodWait as fw:
                await asyncio.sleep(fw.x) # في Pyrogram الحديثة نستخدم .x للثواني
            except Exception:
                continue

        await msg_wait.edit(f"🏁 **اكتمل الإصلاح بنجاح!**\n🎬 فيديوهات: `{count_videos}`\n🖼 بوسترات مربوطة: `{count_linked}`")
    
    except PeerIdInvalid:
        await msg_wait.edit("❌ خطأ: الـ ID غير معروف للبوت. قم بتوجيه رسالة من القناة للبوت أولاً.")
    except Exception as e:
        await msg_wait.edit(f"❌ حدث خطأ غير متوقع:\n`{str(e)}` \nتأكد أن الـ ID يبدأ بـ -100")

# ===== نظام Start والعرض بالحلقات =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    db_execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,), fetch=False)
    
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد في بوت المشاهدة!")
        return

    v_id = message.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        db_execute("UPDATE videos SET views = views + 1 WHERE v_id=?", (v_id,), fetch=False)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

        res = db_execute("SELECT poster_id FROM videos WHERE v_id=?", (v_id,))
        if res and res[0][0]:
            p_id = res[0][0]
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC", (p_id,))
            
            if len(all_ep) > 1:
                btns, row = [], []
                for vid, num in all_ep:
                    label = f"▶️ {num}" if str(vid) == v_id else f"{num if num else '?'}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                    if len(row) == 5: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي حلقات المسلسل:", reply_markup=InlineKeyboardMarkup(btns))

    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك بالقناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ يجب الاشتراك أولاً للمشاهدة.", reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await query.answer("⚠️ اشترك أولاً!", show_alert=True)

app.run()
