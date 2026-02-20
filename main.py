import os
import sqlite3
from datetime import timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# المتغيرات الأساسية
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("SeriesManagerBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def db_query(q, p=(), fetch=True):
    with sqlite3.connect("episodes.db") as conn:
        cur = conn.execute(q, p)
        if fetch:
            return cur.fetchall()
        conn.commit()

db_query("""
CREATE TABLE IF NOT EXISTS episodes (
    v_id TEXT PRIMARY KEY,
    poster_id TEXT,
    ep_num INTEGER,
    quality TEXT,
    duration TEXT
)
""", fetch=False)

# تخزين الحالة الحالية بشكل مؤقت
current_upload = {}

# =========================
# 1️⃣ رفع الفيديو
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    # حساب المدة بدقة للملفات والفيديوهات
    duration_sec = 0
    if message.video:
        duration_sec = message.video.duration
    elif message.document and hasattr(message.document, "duration"):
        duration_sec = message.document.duration

    duration = str(timedelta(seconds=duration_sec)) if duration_sec else "غير معروف"

    # تهيئة عملية رفع جديدة
    current_upload.clear()
    current_upload["v_id"] = str(message.id)
    current_upload["duration"] = duration

    await message.reply_text(
        f"✅ تم استلام الفيديو\n⏱ المدة: {duration}\n🖼 **أرسل الآن البوستر لهذه الحلقة:**",
        quote=True
    )

# =========================
# 2️⃣ رفع البوستر
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    if "v_id" not in current_upload:
        await message.reply_text("⚠️ يرجى رفع الفيديو أولاً.")
        return

    current_upload["poster"] = message.photo.file_id
    await message.reply_text("🖼 تم حفظ البوستر.\n🔢 **أرسل الآن رقم الحلقة:**", quote=True)

# =========================
# 3️⃣ رقم الحلقة (طلب الجودة)
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_episode_number(client, message):
    if "poster" not in current_upload:
        return # يتجاهل الرسالة إذا لم يتم رفع بوستر بعد
        
    if not message.text.isdigit():
        await message.reply_text("❌ يرجى إرسال رقم الحلقة كأرقام فقط.")
        return

    current_upload["ep"] = int(message.text)

    # لن يتم النشر هنا، سننتظر اختيار الجودة
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 HD", callback_data="publish_HD"),
            InlineKeyboardButton("📺 SD", callback_data="publish_SD")
        ]
    ])

    await message.reply_text(f"🔢 الحلقة رقم {message.text} جاهزة.\n⚠️ **اختر الجودة الآن ليتم النشر:**", reply_markup=buttons, quote=True)

# =========================
# 4️⃣ اختيار الجودة والنشر (الخطوة النهائية)
# =========================
@app.on_callback_query(filters.regex("^publish_"))
async def publish_episode(client, query: CallbackQuery):
    if "ep" not in current_upload:
        await query.answer("⚠️ البيانات مفقودة، ابدأ الرفع من جديد.", show_alert=True)
        return

    quality = query.data.split("_")[1] # استخراج HD أو SD
    v_id = current_upload["v_id"]
    poster_id = current_upload["poster"]
    ep = current_upload["ep"]
    duration = current_upload["duration"]

    # 1. الحفظ في قاعدة البيانات
    db_query("""
    INSERT INTO episodes (v_id, poster_id, ep_num, quality, duration)
    VALUES (?, ?, ?, ?, ?)
    """, (v_id, poster_id, ep, quality, duration), fetch=False)

    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"

    caption = (
        f"🎬 **الحلقة {ep}**\n"
        f"✨ **الجودة:** {quality}\n"
        f"⏱ **المدة:** {duration}\n\n"
        f"📥 اضغط الزر أدناه لمشاهدة الحلقة:"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ تشغيل الحلقة", url=watch_link)],
        [InlineKeyboardButton("📺 قائمة جميع الحلقات", callback_data=f"list_{poster_id}")]
    ])

    # 2. النشر الفعلي في القناة العامة
    try:
        await client.send_photo(
            chat_id=PUBLIC_CHANNEL,
            photo=poster_id,
            caption=caption,
            reply_markup=buttons
        )
        await query.message.edit_text(f"🚀 تم النشر بنجاح بجودة {quality} في القناة.")
        # 3. تصفير الحالة بعد النجاح التام
        current_upload.clear()
    except Exception as e:
        await query.message.edit_text(f"❌ خطأ أثناء النشر: {e}")

# =========================
# 5️⃣ عرض الحلقات (Inline)
# =========================
@app.on_callback_query(filters.regex("^list_"))
async def show_all_episodes_inline(client, query: CallbackQuery):
    poster_id = query.data.split("_")[1]

    episodes = db_query("""
    SELECT ep_num, quality, v_id FROM episodes WHERE poster_id=? ORDER BY ep_num ASC
    """, (poster_id,))

    if not episodes:
        await query.answer("❌ لا توجد حلقات مرتبطة بهذا البوستر.", show_alert=True)
        return

    buttons = []
    row = []
    for ep, q, vid in episodes:
        row.append(InlineKeyboardButton(f"• {ep} •", callback_data=f"watch_{vid}"))
        if len(row) == 4: # 4 حلقات في الصف لضمان ظهور الأزرار بشكل جيد
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await query.message.edit_text("📺 اختر الحلقة التي تود مشاهدتها:", reply_markup=InlineKeyboardMarkup(buttons))

# =========================
# 6️⃣ إرسال الفيديو للمستخدم
# =========================
@app.on_callback_query(filters.regex("^watch_"))
async def watch_episode(client, query: CallbackQuery):
    v_id = query.data.split("_")[1]
    try:
        # إرسال نسخة من الفيديو للمستخدم
        await client.copy_message(query.message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        await query.answer("جاري تحميل الحلقة... ⏳")
    except:
        await query.answer("❌ عذراً، الحلقة غير متوفرة حالياً.", show_alert=True)

# =========================
# 7️⃣ معالج البداية (Start)
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        try:
            await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        except:
            await message.reply_text("❌ الرابط غير صالح أو الحلقة محذوفة.")
    else:
        await message.reply_text(f"أهلاً بك يا محمد! 👋\nيرجى استخدام الروابط المنشورة في القناة للمشاهدة.")

app.run()
