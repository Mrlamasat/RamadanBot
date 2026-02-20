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
        if fetch: return cur.fetchall()
        conn.commit()

# حالة الرفع الحالية (تخزين مؤقت)
current_upload = {}

# =========================
# 1️⃣ استلام الفيديو
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = str(timedelta(seconds=duration_sec)) if duration_sec else "غير معروف"

    current_upload.clear()
    current_upload.update({
        "v_id": str(message.id),
        "duration": duration,
        "step": "WAIT_POSTER"
    })
    await message.reply_text(f"✅ تم استلام الفيديو.\n⏱ المدة: {duration}\n🖼 **أرسل البوستر الآن:**", quote=True)

# =========================
# 2️⃣ استلام البوستر + خيار العنوان
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    if current_upload.get("step") != "WAIT_POSTER": return

    current_upload.update({
        "poster": message.photo.file_id,
        "series_tag": str(uuid.uuid4())[:8],
        "default_title": message.caption or "حلقة جديدة",
        "step": "WAIT_TITLE_CHOICE"
    })

    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ استخدام وصف الصورة", callback_data="t_old")],
        [InlineKeyboardButton("✏️ كتابة عنوان جديد", callback_data="t_new")]
    ])
    await message.reply_text("🖼 تم حفظ البوستر. اختر العنوان:", reply_markup=btns, quote=True)

# =========================
# 3️⃣ معالجة العنوان (اختيار قديم أو كتابة جديد)
# =========================
@app.on_callback_query(filters.regex("^t_"))
async def handle_title(client, query: CallbackQuery):
    if query.data == "t_old":
        current_upload.update({"title": current_upload["default_title"], "step": "WAIT_EP"})
        await query.message.edit_text(f"📝 العنوان المعتمد: {current_upload['title']}\n🔢 **أرسل رقم الحلقة الآن:**")
    else:
        current_upload["step"] = "WAIT_TEXT_TITLE"
        await query.message.edit_text("📝 **أرسل العنوان الجديد كرسالة نصية:**")

# =========================
# 4️⃣ استلام النصوص (عنوان جديد أو رقم حلقة)
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def handle_text(client, message):
    # إذا كنا ننتظر العنوان الجديد
    if current_upload.get("step") == "WAIT_TEXT_TITLE":
        current_upload.update({"title": message.text, "step": "WAIT_EP"})
        await message.reply_text(f"✅ العنوان: {message.text}\n🔢 **أرسل الآن رقم الحلقة:**", quote=True)
        return

    # إذا كنا ننتظر رقم الحلقة (هذا هو الشرط ما قبل الأخير)
    if current_upload.get("step") == "WAIT_EP":
        if not message.text.isdigit():
            await message.reply_text("❌ أرسل رقم الحلقة كأرقام فقط.")
            return
        
        current_upload.update({"ep": int(message.text), "step": "WAIT_QUALITY"})
        
        # إظهار أزرار الجودة (بدون نشر)
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("HD", callback_data="q_HD"),
             InlineKeyboardButton("SD", callback_data="q_SD"),
             InlineKeyboardButton("4K", callback_data="q_4K")]
        ])
        await message.reply_text(f"🔢 الحلقة {message.text} جاهزة.\n⚠️ **حدد الجودة الآن ليتم النشر فوراً:**", reply_markup=btns, quote=True)

# =========================
# 5️⃣ اختيار الجودة + النشر التلقائي (الخاتمة)
# =========================
@app.on_callback_query(filters.regex("^q_"))
async def handle_quality_and_publish(client, query: CallbackQuery):
    if current_upload.get("step") != "WAIT_QUALITY":
        await query.answer("⚠️ أكمل البيانات أولاً!", show_alert=True)
        return

    quality = query.data.split("_")[1]
    v_id = current_upload["v_id"]
    poster = current_upload["poster"]
    ep = current_upload["ep"]
    dur = current_upload["duration"]
    tag = current_upload["series_tag"]
    title = current_upload["title"]

    # 1. حفظ البيانات في القاعدة
    db_query("INSERT INTO videos (v_id, duration, title, poster_id, status, ep_num, series_tag) VALUES (?, ?, ?, ?, ?, ?, ?)", 
             (v_id, dur, title, poster, "posted", ep, tag), fetch=False)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = f"🎬 **{title}**\n🔹 الحلقة: {ep}\n✨ الجودة: {quality}\n⏱ المدة: {dur}\n\n📥 [مشاهدة الآن]({watch_link})"

    try:
        # 2. النشر الفعلي في القناة العامة
        await client.send_photo(
            chat_id=PUBLIC_CHANNEL,
            photo=poster,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        )
        await query.message.edit_text(f"🚀 تم النشر بنجاح بجودة {quality}!")
        current_upload.clear() # تصفير الحالة لاستقبال عملية جديدة
    except Exception as e:
        await query.message.edit_text(f"❌ خطأ في النشر: {e}")

app.run()
