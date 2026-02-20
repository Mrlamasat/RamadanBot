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

# قاموس الجلسات لتخزين البيانات مؤقتاً
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
    
    # بدء الجلسة وربطها بـ ID الرسالة
    sessions[v_id] = {
        "v_id": v_id,
        "duration": duration,
        "step": "WAIT_POSTER"
    }

    await message.reply_text(
        f"✅ تم استلام الفيديو.\n⏱ المدة: {duration}\n👈 **يرجى الرد (Reply) على هذه الرسالة بالبوستر.**",
        quote=True
    )

# =========================
# 2️⃣ استلام البوستر (يجب الرد على رسالة البوت)
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    # الحصول على ID الرسالة الأصلية التي تم الرد عليها
    reply_to_id = str(message.reply_to_message.reply_to_message.id) if message.reply_to_message and message.reply_to_message.reply_to_message else None
    
    # محاولة جلب الجلسة عبر الرد المباشر أو غير المباشر
    v_id = None
    for sid in sessions:
        if message.reply_to_message and str(message.reply_to_message.id) in str(sessions[sid].get("last_msg_id", "")):
            v_id = sid
            break
    
    # إذا لم نجدها، نستخدم المنطق الافتراضي للرد
    if not v_id and message.reply_to_message:
        # نبحث في الجلسات عن الجلسة التي تنتظر بوستر
        for sid, sess in sessions.items():
            if sess["step"] == "WAIT_POSTER":
                v_id = sid
                break

    if not v_id or sessions[v_id]["step"] != "WAIT_POSTER":
        return

    # حفظ العنوان إذا وُجد في وصف الصورة
    title = message.caption if message.caption else ""

    sessions[v_id].update({
        "poster": message.photo.file_id,
        "title": title,
        "step": "WAIT_EP_NUM"
    })

    sent_msg = await message.reply_text(
        f"🖼 تم حفظ البوستر.\n📝 العنوان الحالي: {title if title else 'بدون عنوان'}\n👈 **الآن قم بالرد على هذه الرسالة برقم الحلقة:**",
        quote=True
    )
    sessions[v_id]["last_msg_id"] = sent_msg.id

# =========================
# 3️⃣ استلام رقم الحلقة
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def handle_episode_number(client, message):
    v_id = None
    for sid, sess in sessions.items():
        if sess["step"] == "WAIT_EP_NUM":
            v_id = sid
            break
            
    if not v_id or not message.text.isdigit():
        return

    sessions[v_id].update({"ep": int(message.text), "step": "WAIT_QUALITY_CLICK"})

    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 HD", callback_data=f"final_HD|{v_id}"),
         InlineKeyboardButton("📺 SD", callback_data=f"final_SD|{v_id}"),
         InlineKeyboardButton("🔥 4K", callback_data=f"final_4K|{v_id}")]
    ])
    
    await message.reply_text(
        f"🔢 الحلقة رقم: {message.text}\n⚠️ **اختر الجودة الآن ليتم النشر:**",
        reply_markup=btns, quote=True
    )

# =========================
# 4️⃣ اختيار الجودة والنشر النهائي
# =========================
@app.on_callback_query(filters.regex("^final_"))
async def finalize_and_post(client, query: CallbackQuery):
    data_parts = query.data.split("|")
    quality_part = data_parts[0].split("_")[1]
    v_id = data_parts[1]
    
    session = sessions.get(v_id)
    if not session or session.get("step") != "WAIT_QUALITY_CLICK":
        await query.answer("⚠️ البيانات منتهية الصلاحية!", show_alert=True)
        return

    # استخراج البيانات
    poster = session["poster"]
    ep = session["ep"]
    dur = session["duration"]
    title = session["title"]

    # حفظ في قاعدة البيانات
    db_query(
        "INSERT INTO videos (v_id, duration, poster_id, status, ep_num, quality, title) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (v_id, dur, poster, "posted", ep, quality_part, title),
        fetch=False
    )

    bot_me = await client.get_me()
    watch_link = f"https://t.me/{bot_me.username}?start={v_id}"

    # تنسيق الرسالة النهائية
    caption = f"🎬 **{title}**\n" if title else ""
    caption += (f"🔹 الحلقة: {ep}\n"
                f"✨ الجودة: {quality_part}\n"
                f"⏱ المدة: {dur}\n\n"
                f"📥 اضغط الزر أدناه لمشاهدة الحلقة:")

    try:
        await client.send_photo(
            chat_id=PUBLIC_CHANNEL,
            photo=poster,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        )
        await query.message.edit_text(f"🚀 **تم النشر بنجاح!**\n🎬 {title}\n🔢 الحلقة {ep}\n✨ الجودة: {quality_part}")
        sessions.pop(v_id, None) # مسح الجلسة بعد النجاح
    except Exception as e:
        await query.message.edit_text(f"❌ حدث خطأ أثناء النشر:\n`{str(e)}`")

app.run()
