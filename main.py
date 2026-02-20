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
        if fetch: return cur.fetchall()
        conn.commit()

# جلسة العمل النشطة
active_session = {}

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
    
    active_session.clear()
    active_session.update({
        "v_id": str(message.id),
        "duration": duration,
        "step": "WAIT_POSTER"
    })

    await message.reply_text(
        f"✅ تم استلام الفيديو.\n⏱ المدة: {duration}\n\n👈 **أرسل البوستر الآن (يمكنك كتابة وصف أو تركه فارغاً):**",
        quote=True
    )

# =========================
# 2️⃣ استلام البوستر + الانتقال للجودة فوراً
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    if active_session.get("step") != "WAIT_POSTER":
        return

    # استلام الوصف (اختياري)
    description = message.caption if message.caption else ""

    active_session.update({
        "poster": message.photo.file_id,
        "description": description,
        "step": "WAIT_QUALITY"
    })

    # إظهار خيارات الجودة فوراً بعد استلام البوستر
    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 HD", callback_data="set_HD"),
         InlineKeyboardButton("📺 SD", callback_data="set_SD"),
         InlineKeyboardButton("🔥 4K", callback_data="set_4K")]
    ])
    
    await message.reply_text(
        f"🖼 تم استلام البوستر.\n📝 الوصف: {description if description else 'لا يوجد'}\n\n👈 **حدد الجودة المطلوبة للنشر الآن:**",
        reply_markup=btns, quote=True
    )

# =========================
# 3️⃣ تحديد الجودة + النشر التلقائي
# =========================
@app.on_callback_query(filters.regex("^set_"))
async def finalize_and_post(client, query: CallbackQuery):
    if active_session.get("step") != "WAIT_QUALITY":
        await query.answer("⚠️ البيانات غير مكتملة، يرجى البدء من جديد.", show_alert=True)
        return

    quality = query.data.split("_")[1]
    
    # استخراج البيانات
    v_id = active_session["v_id"]
    poster = active_session["poster"]
    desc = active_session["description"]
    dur = active_session["duration"]

    # رابط المشاهدة (البوت)
    bot_me = await client.get_me()
    watch_link = f"https://t.me/{bot_me.username}?start={v_id}"

    # تنسيق البوست النهائي حسب المواصفات
    # إذا كان هناك وصف يظهر في البداية، ثم تفاصيل الجودة والمدة
    caption = f"🎬 **{desc}**\n\n" if desc else ""
    caption += (f"✨ الجودة: {quality}\n"
                f"⏱ المدة: {dur}\n\n"
                f"📥 اضغط الزر أدناه لمشاهدة الحلقة:")

    try:
        # إرسال البوست للقناة العامة
        await client.send_photo(
            chat_id=PUBLIC_CHANNEL,
            photo=poster,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        )
        
        # حفظ في قاعدة البيانات للتوثيق
        db_query(
            "INSERT INTO videos (v_id, duration, poster_id, status, quality, title) VALUES (?, ?, ?, ?, ?, ?)",
            (v_id, dur, poster, "posted", quality, desc),
            fetch=False
        )

        await query.message.edit_text(f"🚀 **تم النشر بنجاح!**\nالمنشور الآن في القناة: {PUBLIC_CHANNEL}")
        
        # تصفير الجلسة لاستقبال فيديو جديد
        active_session.clear()
        
    except Exception as e:
        await query.message.edit_text(f"❌ حدث خطأ أثناء النشر:\n`{str(e)}`")

app.run()
