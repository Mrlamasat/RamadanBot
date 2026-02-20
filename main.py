import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية (تُجلب من إعدادات Railway) =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

if not all([API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID, PUBLIC_CHANNEL]):
    logging.error("❌ تأكد من إعداد جميع المتغيرات البيئية API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID, PUBLIC_CHANNEL")
    exit(1)

app = Client("SmartSeriesBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== دالة تهيئة قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, poster_file_id TEXT, ep_num INTEGER, status TEXT)''')
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
    if not seconds: return "غير متوفر"
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d} دقيقة"

# ===== استقبال الفيديو أو المستند =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    try:
        duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
        duration_str = format_duration(duration_sec)
        db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
                   (str(message.id), duration_str, "waiting"), fetch=False)
        await message.reply_text(f"✅ تم استلام الفيديو (ID: {message.id})\nالآن أرسل **البوستر (الصورة)** لهذا الفيديو.")
    except Exception as e:
        logging.exception(f"❌ خطأ في receive_video: {e}")

# ===== استقبال البوستر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    try:
        res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
        if not res: return
        v_id = res[0][0]
        db_execute(
            "UPDATE videos SET title = ?, poster_id = ?, poster_file_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
            (message.caption or "حلقة جديدة", message.photo.file_id, message.photo.file_id, v_id), fetch=False
        )
        await message.reply_text(f"📌 تم ربط البوستر.\nالآن أرسل **رقم الحلقة** (أرقام فقط):")
    except Exception as e:
        logging.exception(f"❌ خطأ في receive_poster: {e}")

# ===== استقبال رقم الحلقة =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start", "edit", "list"]))
async def receive_ep_number(client, message):
    try:
        res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
        if not res or not message.text.isdigit(): return
        v_id = res[0][0]
        db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("HD 720p", callback_data=f"q_HD_{v_id}"),
             InlineKeyboardButton("SD 480p", callback_data=f"q_SD_{v_id}")]
        ])
        await message.reply_text(f"✅ تم تسجيل الحلقة {message.text}.\nاختر الجودة للنشر في القناة العامة:", reply_markup=markup)
    except Exception as e:
        logging.exception(f"❌ خطأ في receive_ep_number: {e}")

# ===== اختيار الجودة =====
@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    try:
        _, quality, v_id = query.data.split("_")
        res = db_execute("SELECT duration, title, poster_id, ep_num FROM videos WHERE v_id = ?", (v_id,))
        if not res: return
        duration, title, p_id, ep_num = res[0]
        bot_info = await client.get_me()
        link = f"https://t.me/{bot_info.username}?start={v_id}"
        caption_text = (f"🎬 **{title}**\n\n"
                        f"🔢 رقم الحلقة: {ep_num}\n"
                        f"⏱ المدة: {duration}\n"
                        f"✨ الجودة: {quality}\n\n"
                        f"📥 [اضغط هنا للمشاهدة الآن]({link})")
        await client.send_photo(
            f"@{PUBLIC_CHANNEL}", photo=p_id, caption=caption_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]])
        )
        db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
        await query.message.edit_text("✅ تم النشر بنجاح في القناة العامة!")
    except Exception as e:
        logging.exception(f"❌ خطأ في quality_callback: {e}")
        await query.answer("❌ حدث خطأ أثناء النشر.", show_alert=True)

# ===== دالة /start محسنة =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    try:
        user_id = message.from_user.id
        first_name = message.from_user.first_name or "صديق"

        # حالة /start فقط بدون v_id
        if len(message.command) == 1:
            await message.reply_text(f"أهلاً بك يا {first_name} في بوت المسلسلات! 🌙\n\n"
                                     f"أرسل /start <رقم_الحلقة> لمشاهدة حلقة محددة.")
            return

        # حالة /start مع v_id
        v_id = message.command[1]

        # التحقق من الاشتراك الإجباري
        try:
            await client.get_chat_member(f"@{PUBLIC_CHANNEL}", user_id)
        except UserNotParticipant:
            btn = [
                [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
                [InlineKeyboardButton("✅ تم الاشتراك، أرسل الفيديو", callback_data=f"chk_{v_id}")]
            ]
            await message.reply_text(
                "⚠️ يجب عليك الاشتراك في القناة أولاً لمشاهدة الفيديو.",
                reply_markup=InlineKeyboardMarkup(btn)
            )
            return

        # إرسال الفيديو
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

        # عرض باقي الحلقات لنفس المسلسل
        video_data = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if video_data and video_data[0][0]:
            p_id = video_data[0][0]
            all_ep = db_execute(
                "SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC",
                (p_id,)
            )
            if len(all_ep) > 1:
                btns = []
                row = []
                bot_info = await client.get_me()
                for v_id_item, num in all_ep:
                    label = f"الحلقة {num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id_item}"))
                    if len(row) == 2:
                        btns.append(row)
                        row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي حلقات المسلسل:", reply_markup=InlineKeyboardMarkup(btns))

    except Exception as e:
        logging.exception(f"❌ خطأ في /start: {e}")
        await message.reply_text(f"❌ حدث خطأ أثناء معالجة /start.\nالرجاء المحاولة لاحقاً.")

# ===== تحقق الاشتراك بعد الضغط على زر "تم الاشتراك" =====
@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub_callback(client, query):
    try:
        v_id = query.data.split("_")[1]
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except UserNotParticipant:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)
    except Exception as e:
        logging.exception(f"❌ خطأ في check_sub_callback: {e}")
        await query.answer("❌ حدث خطأ داخلي.", show_alert=True)

print("🚀 البوت يعمل الآن بنجاح...")
app.run()
