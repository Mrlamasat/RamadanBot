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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            duration INTEGER,
            poster_id TEXT,
            status TEXT,
            ep_num INTEGER,
            user_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=True):
    with sqlite3.connect("bot_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.fetchall() if fetch else None

def format_duration(seconds):
    if not seconds:
        return "غير محدد"
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d} دقيقة"

# ===== 1. استلام الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)

    # التحقق من آخر poster_id موجود (لإضافة الحلقة لمسلسل قديم)
    last_poster = db_execute(
        "SELECT poster_id FROM videos WHERE status='posted' ORDER BY rowid DESC LIMIT 1"
    )
    poster_id = last_poster[0][0] if last_poster else None

    db_execute(
        "INSERT INTO videos (v_id, duration, poster_id, status, user_id) VALUES (?, ?, ?, ?, ?)",
        (v_id, duration_sec, poster_id, "waiting", message.from_user.id),
        fetch=False
    )
    await message.reply_text("✅ تم استلام الفيديو.\n🖼 الآن أرسل البوستر أو تجاهل إذا المسلسل موجود مسبقاً.")

# ===== 2. استلام البوستر (اختياري) =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute(
        "SELECT v_id FROM videos WHERE status='waiting' AND user_id=? ORDER BY rowid DESC LIMIT 1",
        (message.from_user.id,)
    )
    if not res:
        return
    v_id = res[0][0]

    # تحديث البوستر فقط إذا لم يكن موجود مسبقاً
    current_poster = db_execute("SELECT poster_id FROM videos WHERE v_id=?", (v_id,))
    if not current_poster[0][0]:
        db_execute(
            "UPDATE videos SET poster_id=?, status='awaiting_ep' WHERE v_id=?",
            (message.photo.file_id, v_id),
            fetch=False
        )
    else:
        # إذا يوجد poster_id مسبقاً، فقط تحديث الحالة
        db_execute(
            "UPDATE videos SET status='awaiting_ep' WHERE v_id=?",
            (v_id,),
            fetch=False
        )
    await message.reply_text("🖼 تم حفظ البوستر أو استخدام البوستر السابق.\n🔢 أرسل الآن رقم الحلقة:")

# ===== 3. استلام رقم الحلقة =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    if not message.text.isdigit():
        return
    res = db_execute(
        "SELECT v_id FROM videos WHERE status='awaiting_ep' AND user_id=? ORDER BY rowid DESC LIMIT 1",
        (message.from_user.id,)
    )
    if not res:
        return
    v_id = res[0][0]
    ep_num = int(message.text)
    db_execute(
        "UPDATE videos SET ep_num=?, status='ready' WHERE v_id=?",
        (ep_num, v_id),
        fetch=False
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("SD", callback_data=f"p_SD_{v_id}"),
         InlineKeyboardButton("HD", callback_data=f"p_HD_{v_id}"),
         InlineKeyboardButton("4K", callback_data=f"p_4K_{v_id}")]
    ])
    await message.reply_text(f"✅ الحلقة {ep_num} جاهزة. اختر الجودة للنشر:", reply_markup=markup)

# ===== 4. النشر في القناة =====
@app.on_callback_query(filters.regex(r"^p_"))
async def publish_now(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT ep_num, poster_id, duration FROM videos WHERE v_id=?", (v_id,))
    if not res:
        await query.message.edit_text("❌ خطأ: لم يتم العثور على البيانات.")
        return
    ep_num, poster_id, duration = res[0]
    duration_str = format_duration(duration)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = (f"🎬 الحلقة {ep_num}\n"
               f"⏱ المدة: {duration_str}\n"
               f"✨ الجودة: {quality}\n\n"
               f"📥 مشاهدة الآن")
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=watch_link)]])

    try:
        await client.send_video(chat_id=f"@{PUBLIC_CHANNEL}", video=int(v_id), thumb=poster_id, caption=caption, reply_markup=markup)
        db_execute("UPDATE videos SET status='posted' WHERE v_id=?", (v_id,), fetch=False)
        await query.message.edit_text("🚀 تم النشر بنجاح.")
    except Exception as e:
        await query.message.edit_text(f"❌ خطأ في النشر: {e}")

# ===== 5. تشغيل الفيديو وقائمة الحلقات =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text("أهلاً بك!")
        return
    v_id = message.command[1]

    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", message.from_user.id)
    except UserNotParticipant:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{PUBLIC_CHANNEL}")],
            [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]
        ])
        await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=markup)
        return
    await send_video_with_list(client, message.chat.id, v_id)

async def send_video_with_list(client, chat_id, v_id):
    try:
        await client.copy_message(chat_id, CHANNEL_ID, int(v_id), protect_content=True)
    except Exception as e:
        logging.error(f"Error sending video: {e}")
        await client.send_message(chat_id, "❌ الحلقة غير متوفرة حالياً.")
        return

    # عرض قائمة الحلقات لكل الحلقات بنفس poster_id
    try:
        res = db_execute("SELECT poster_id FROM videos WHERE v_id=?", (v_id,))
        if res and res[0][0]:
            poster_id = res[0][0]
            all_eps = db_execute(
                "SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC",
                (poster_id,)
            )

            if len(all_eps) > 1:
                buttons = []; row = []
                bot_username = (await client.get_me()).username
                for vid, num in all_eps:
                    text = f"▶️ {num}" if vid == v_id else f"{num}"
                    row.append(InlineKeyboardButton(text, url=f"https://t.me/{bot_username}?start={vid}"))
                    if len(row) == 4:
                        buttons.append(row); row = []
                if row: buttons.append(row)
                await client.send_message(chat_id, "📥 شاهد المزيد من الحلقات:", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logging.error(f"Error sending episode list: {e}")

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", query.from_user.id)
        await query.message.delete()
        await send_video_with_list(client, query.from_user.id, v_id)
    except UserNotParticipant:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)

app.run()
