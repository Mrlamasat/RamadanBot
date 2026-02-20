import os
import sqlite3
from datetime import timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("SmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def db_query(q, p=(), fetch=True):
    with sqlite3.connect("bot_data.db") as conn:
        cur = conn.execute(q, p)
        if fetch:
            return cur.fetchall()
        conn.commit()

db_query("""CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    v_id TEXT,
    duration TEXT,
    poster_id TEXT,
    status TEXT,
    ep_num INTEGER,
    series_tag TEXT,
    quality TEXT,
    title TEXT
)""", fetch=False)

sessions = {}

# =========================
# 1️⃣ استلام الفيديو
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration_sec = 0
    if message.video:
        duration_sec = message.video.duration
    elif message.document and getattr(message.document, "duration", None):
        duration_sec = message.document.duration

    duration = str(timedelta(seconds=duration_sec)) if duration_sec else "غير معروف"
    v_id = str(message.id)
    sessions[v_id] = {
        "v_id": v_id,
        "duration": duration,
        "step": "WAIT_POSTER"
    }

    await message.reply_text(
        f"✅ تم استلام الفيديو.\n⏱ المدة: {duration}\n👈 الآن أرسل البوستر.",
        quote=True
    )

# =========================
# 2️⃣ استلام البوستر
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    v_id = str(message.reply_to_message.id) if message.reply_to_message else None
    session = sessions.get(v_id)
    if not session or session.get("step") != "WAIT_POSTER":
        return

    # استخدم caption كعنوان إذا كتبته، وإلا فارغ
    title = message.caption if message.caption else ""

    session.update({
        "poster": message.photo.file_id,
        "series_tag": str(v_id),
        "title": title,   # العنوان من caption أو فارغ
        "step": "WAIT_EP_NUM"
    })

    await message.reply_text(
        "🖼 تم حفظ البوستر.\n👈 أرسل رقم الحلقة (أرقام فقط).",
        quote=True
    )

# =========================
# 3️⃣ استلام رقم الحلقة
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def handle_episode_number(client, message):
    v_id = str(message.reply_to_message.id) if message.reply_to_message else None
    session = sessions.get(v_id)
    if not session or session.get("step") != "WAIT_EP_NUM":
        return

    if not message.text.isdigit():
        await message.reply_text("❌ يرجى إرسال رقم الحلقة فقط (أرقام).")
        return

    session.update({"ep": int(message.text), "step": "WAIT_QUALITY_CLICK"})

    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 HD", callback_data=f"final_HD|{v_id}"),
         InlineKeyboardButton("📺 SD", callback_data=f"final_SD|{v_id}"),
         InlineKeyboardButton("🔥 4K", callback_data=f"final_4K|{v_id}")]
    ])
    await message.reply_text(
        f"🔢 الحلقة رقم: {message.text}\n⚠️ اختر الآن الجودة المطلوبة:",
        reply_markup=btns, quote=True
    )

# =========================
# 4️⃣ اختيار الجودة والنشر النهائي
# =========================
@app.on_callback_query(filters.regex("^final_"))
async def finalize_and_post(client, query: CallbackQuery):
    await query.answer()
    data, v_id = query.data.split("|")
    session = sessions.get(v_id)
    if not session or session.get("step") != "WAIT_QUALITY_CLICK":
        await query.answer("⚠️ البيانات غير مكتملة!", show_alert=True)
        return

    quality = data.split("_")[1]
    poster = session["poster"]
    ep = session["ep"]
    dur = session["duration"]
    tag = session["series_tag"]
    title = session["title"]  # من caption أو فارغ

    db_query(
        "INSERT INTO videos (v_id, duration, poster_id, status, ep_num, series_tag, quality, title) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (v_id, dur, poster, "posted", ep, tag, quality, title),
        fetch=False
    )

    bot_me = await client.get_me()
    watch_link = f"https://t.me/{bot_me.username}?start={v_id}"

    # إذا كان العنوان فارغ لا يظهر أي شيء، وإلا يظهر العنوان
    caption = f"{title}\n" if title else ""
    caption += (f"🔹 الحلقة: {ep}\n"
                f"✨ الجودة: {quality}\n"
                f"⏱ المدة: {dur}\n\n"
                f"📥 اضغط الزر أدناه لمشاهدة الحلقة:")

    try:
        await client.send_photo(
            chat_id=PUBLIC_CHANNEL,
            photo=poster,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        )
        await query.message.edit_text(f"🚀 تم النشر بنجاح! | الحلقة {ep} | الجودة: {quality}")
        sessions.pop(v_id, None)
    except Exception as e:
        await query.message.edit_text(f"❌ حدث خطأ أثناء النشر:\n`{str(e)}`")

app.run()
