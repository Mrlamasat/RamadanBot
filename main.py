import os
import sqlite3
import logging
from datetime import timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ===== Logging =====
logging.basicConfig(level=logging.INFO)

# ===== Config =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("SeriesBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Database =====
def init_db():
    with sqlite3.connect("bot.db") as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            poster_id TEXT,
            ep_num INTEGER,
            quality TEXT,
            duration TEXT
        )
        """)

init_db()

def db_execute(q, p=(), fetch=True):
    with sqlite3.connect("bot.db") as conn:
        cur = conn.execute(q, p)
        if fetch:
            return cur.fetchall()
        conn.commit()
        return None

# ===== State (متغير واحد لتخزين الحالة المؤقتة) =====
current_video = {
    "v_id": None,
    "duration": None,
    "poster_id": None,
    "ep_num": None
}

# =========================
# 1️⃣ استقبال الفيديو
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    global current_video
    
    v_id = str(message.id)
    
    if message.video:
        duration = str(timedelta(seconds=message.video.duration))
    elif message.document and hasattr(message.document, "duration"):
        duration = str(timedelta(seconds=message.document.duration))
    else:
        duration = "غير معروف"

    # تهيئة الحالة الجديدة
    current_video = {
        "v_id": v_id,
        "duration": duration,
        "poster_id": None,
        "ep_num": None
    }

    await message.reply_text("✅ تم استلام الفيديو.\n🖼 أرسل الآن **البوستر** (صورة فقط).")

# =========================
# 2️⃣ استقبال البوستر
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    global current_video

    if not current_video["v_id"]:
        await message.reply_text("⚠️ يرجى رفع الفيديو أولاً.")
        return

    current_video["poster_id"] = message.photo.file_id
    await message.reply_text("🖼 تم حفظ البوستر.\n🔢 أرسل الآن **رقم الحلقة**.")

# =========================
# 3️⃣ استقبال رقم الحلقة
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep(client, message):
    global current_video

    if not current_video.get("poster_id"):
        await message.reply_text("⚠️ يرجى إرسال البوستر أولاً.")
        return

    if not message.text.isdigit():
        await message.reply_text("❌ أرسل **رقم الحلقة** كأرقام فقط.")
        return

    current_video["ep_num"] = int(message.text)

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 HD", callback_data="HD"),
            InlineKeyboardButton("📺 SD", callback_data="SD")
        ]
    ])

    await message.reply_text(f"✨ الحلقة {message.text} جاهزة.\nاختر الجودة المطلوبة للنشر:", reply_markup=buttons)

# =========================
# 4️⃣ اختيار الجودة والنشر
# =========================
@app.on_callback_query()
async def publish(client, query: CallbackQuery):
    global current_video

    if not current_video.get("ep_num"):
        await query.answer("⚠️ البيانات غير مكتملة، ابدأ برفع الفيديو من جديد.", show_alert=True)
        return

    quality = query.data
    v_id = current_video["v_id"]
    poster_id = current_video["poster_id"]
    ep_num = current_video["ep_num"]
    duration = current_video["duration"]

    # حفظ البيانات في قاعدة البيانات
    db_execute("""
    INSERT OR REPLACE INTO videos 
    (v_id, poster_id, ep_num, quality, duration)
    VALUES (?, ?, ?, ?, ?)
    """, (v_id, poster_id, ep_num, quality, duration), fetch=False)

    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    caption = (
        f"🎬 **حلقة جديدة جاهزة**\n\n"
        f"🔹 **رقم الحلقة:** {ep_num}\n"
        f"✨ **الجودة:** {quality}\n"
        f"⏱ **المدة:** {duration}\n\n"
        f"📥 لمشاهدة الحلقة اضغط على الزر أدناه:"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ تشغيل الحلقة الآن", url=watch_link)]
    ])

    # النشر في القناة العامة
    try:
        await client.send_photo(
            chat_id=PUBLIC_CHANNEL,
            photo=poster_id,
            caption=caption,
            reply_markup=buttons
        )
        await query.message.edit_text(f"🚀 تم النشر بنجاح في القناة العامة بجودة {quality}.")
    except Exception as e:
        await query.message.edit_text(f"⚠️ فشل النشر في القناة: {e}")

    # تصفير الحالة لاستقبال فيديو جديد
    current_video = {"v_id": None, "duration": None, "poster_id": None, "ep_num": None}

# =========================
# 5️⃣ تشغيل الحلقة
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) == 1:
        await message.reply_text(f"أهلاً بك يا محمد! 👋\nيرجى استخدام روابط الحلقات المنشورة لمشاهدة المحتوى.")
        return

    arg = message.command[1]
    
    # محاولة إرسال الحلقة
    try:
        # استرجاع بيانات الحلقة لعرض وصف بسيط
        data = db_execute("SELECT ep_num, quality FROM videos WHERE v_id=?", (arg,))
        if data:
            ep, q = data[0]
            await message.reply_text(f"🎬 جاري تجهيز الحلقة {ep} ({q})...")
        
        await client.copy_message(message.chat.id, CHANNEL_ID, int(arg), protect_content=True)
    except:
        await message.reply_text("❌ عذراً، هذه الحلقة لم تعد متوفرة.")

app.run()
