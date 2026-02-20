import os
import sqlite3
import uuid
from datetime import timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def db_query(q, p=(), fetch=True):
    with sqlite3.connect("bot_data.db") as conn:
        cur = conn.execute(q, p)
        if fetch:
            return cur.fetchall()
        conn.commit()

# إنشاء جدول الفيديوهات إذا لم يكن موجودًا
db_query("""CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    v_id TEXT,
    duration TEXT,
    title TEXT,
    poster_id TEXT,
    status TEXT,
    ep_num INTEGER,
    series_tag TEXT
)""", fetch=False)

# قاموس الجلسات لكل فيديو
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
        f"✅ **تم استلام الفيديو.**\n⏱ المدة: {duration}\n\n👈 **الآن أرسل البوستر (الصورة):**",
        quote=True
    )

# =========================
# 2️⃣ استلام البوستر
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    # نجد الجلسة الأخيرة للفيديو المرسل من نفس المستخدم
    v_id = str(message.reply_to_message.id) if message.reply_to_message else None
    session = sessions.get(v_id)
    if not session or session.get("step") != "WAIT_POSTER":
        return

    session.update({
        "poster": message.photo.file_id,
        "series_tag": str(uuid.uuid4())[:8],
        "default_title": message.caption if message.caption else "حلقة جديدة",
        "step": "WAIT_TITLE_CHOICE"
    })

    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ استخدام وصف الصورة", callback_data=f"choice_old|{v_id}")],
        [InlineKeyboardButton("✏️ كتابة عنوان جديد", callback_data=f"choice_new|{v_id}")]
    ])
    await message.reply_text(
        "🖼 **تم حفظ البوستر.**\nحدد كيف تود وضع العنوان للمسلسل:",
        reply_markup=btns, quote=True
    )

# =========================
# 3️⃣ معالجة خيار العنوان
# =========================
@app.on_callback_query(filters.regex("^choice_"))
async def handle_title_selection(client, query: CallbackQuery):
    await query.answer()
    data, v_id = query.data.split("|")
    session = sessions.get(v_id)
    if not session or session.get("step") != "WAIT_TITLE_CHOICE":
        await query.answer("⚠️ حدث خطأ في الترتيب، أعد رفع الفيديو.", show_alert=True)
        return

    if data == "choice_old":
        session.update({"title": session["default_title"], "step": "WAIT_EP_NUM"})
        await query.message.edit_text(
            f"📝 العنوان المعتمد: **{session['title']}**\n\n👈 **أرسل الآن رقم الحلقة فقط:**"
        )
    else:
        session["step"] = "WAIT_TEXT_INPUT"
        await query.message.edit_text("📝 **أرسل الآن اسم المسلسل (نص):**")

# =========================
# 4️⃣ استلام النصوص
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def handle_all_text(client, message):
    # نبحث عن الجلسة المرتبطة برسالة الفيديو الأخيرة
    v_id = str(message.reply_to_message.id) if message.reply_to_message else None
    session = sessions.get(v_id)
    if not session:
        return

    step = session.get("step")

    if step == "WAIT_TEXT_INPUT":
        session.update({"title": message.text, "step": "WAIT_EP_NUM"})
        await message.reply_text(f"✅ تم اعتماد العنوان: **{message.text}**\n\n👈 **أرسل الآن رقم الحلقة:**", quote=True)
        return

    if step == "WAIT_EP_NUM":
        if not message.text.isdigit():
            await message.reply_text("❌ خطأ: يرجى إرسال **رقم الحلقة فقط** (أرقام).")
            return

        session.update({"ep": int(message.text), "step": "WAIT_QUALITY_CLICK"})
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 HD", callback_data=f"final_HD|{v_id}"),
             InlineKeyboardButton("📺 SD", callback_data=f"final_SD|{v_id}"),
             InlineKeyboardButton("🔥 4K", callback_data=f"final_4K|{v_id}")]
        ])
        await message.reply_text(
            f"🔢 الحلقة رقم: **{message.text}**\n\n⚠️ **الآن حدد الجودة المطلوبة ليتم النشر فوراً:**",
            reply_markup=btns, quote=True
        )

# =========================
# 5️⃣ اختيار الجودة + النشر النهائي
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
    title = session["title"]

    db_query(
        "INSERT INTO videos (v_id, duration, title, poster_id, status, ep_num, series_tag) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (v_id, dur, title, poster, "posted", ep, tag), fetch=False
    )

    bot_me = await client.get_me()
    watch_link = f"https://t.me/{bot_me.username}?start={v_id}"

    caption = (f"🎬 **{title}**\n"
               f"🔹 **الحلقة:** {ep}\n"
               f"✨ **الجودة:** {quality}\n"
               f"⏱ **المدة:** {dur}\n\n"
               f"📥 اضغط الزر أدناه لمشاهدة الحلقة:")

    try:
        await client.send_photo(
            chat_id=PUBLIC_CHANNEL,
            photo=poster,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        )
        await query.message.edit_text(f"🚀 **تم النشر بنجاح!**\nالجودة: {quality} | الحلقة: {ep}")
        # إزالة الجلسة بعد النشر
        sessions.pop(v_id, None)

    except Exception as e:
        await query.message.edit_text(f"❌ **حدث خطأ أثناء النشر:**\n`{str(e)}`")

app.run()
