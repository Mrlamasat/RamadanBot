import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from datetime import timedelta

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def init_db():
    with sqlite3.connect("bot_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                v_id TEXT PRIMARY KEY,
                title TEXT,
                poster_id TEXT,
                status TEXT,
                ep_num INTEGER,
                quality TEXT,
                duration TEXT
            )
        ''')
init_db()

def db_execute(query, params=(), fetch=True):
    with sqlite3.connect("bot_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.fetchall() if fetch else None

# ===== 1. استقبال الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    
    # حساب مدة الفيديو
    duration = None
    if message.video:
        duration = str(timedelta(seconds=message.video.duration))
    elif message.document and message.document.mime_type.startswith("video/"):
        duration = "غير معروف"

    db_execute(
        "INSERT OR REPLACE INTO videos (v_id, status, duration) VALUES (?, ?, ?)",
        (v_id, "waiting", duration), fetch=False
    )
    await message.reply_text(
        f"✅ تم استلام الفيديو (ID: {v_id})\n🖼 الآن أرسل البوستر (صورة واحدة لكل المسلسل)."
    )

# ===== 2. استقبال البوستر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res:
        await message.reply_text("⚠️ لم يتم العثور على فيديو لربطه بالبوستر. ارفع الفيديو أولاً.")
        return

    v_id = res[0][0]
    db_execute(
        "UPDATE videos SET poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
        (message.photo.file_id, v_id), fetch=False
    )
    await message.reply_text("🖼 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة:")

# ===== 3. استقبال رقم الحلقة وعرض أزرار الجودة =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    if not message.text.isdigit():
        await message.reply_text("❌ يرجى إرسال رقم الحلقة فقط.")
        return

    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res:
        await message.reply_text("⚠️ لم يتم العثور على فيديو جاهز لتحديد رقم الحلقة.")
        return

    v_id = res[0][0]
    ep_num = int(message.text)
    db_execute(
        "UPDATE videos SET ep_num = ?, status = 'awaiting_quality' WHERE v_id = ?",
        (ep_num, v_id), fetch=False
    )

    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 HD", callback_data=f"setq_HD_{v_id}"),
            InlineKeyboardButton("📺 SD", callback_data=f"setq_SD_{v_id}")
        ]
    ])
    await message.reply_text(f"✅ تم تحديد رقم الحلقة {ep_num}.\n✨ اختر الجودة:", reply_markup=btns)

# ===== 4. معالجة اختيار الجودة والنشر =====
@app.on_callback_query(filters.regex(r"^setq_"))
async def publish_handler(client, query: CallbackQuery):
    data = query.data.split("_")
    quality = data[1]
    v_id = data[2]

    res = db_execute("SELECT ep_num, poster_id, duration FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    ep_num, poster_id, duration = res[0]

    db_execute("UPDATE videos SET quality = ?, status = 'posted' WHERE v_id = ?", (quality, v_id), fetch=False)

    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"
    more_episodes_link = f"https://t.me/{bot_info.username}?start=series_{poster_id}"

    if PUBLIC_CHANNEL:
        try:
            caption = f"🔹 رقم الحلقة: {ep_num}\n✨ الجودة: {quality}\n⏱ مدة الحلقة: {duration}\n\n📥 لمشاهدة الحلقة اضغط على الزر أدناه:"
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ تشغيل الحلقة", url=watch_link)],
                [InlineKeyboardButton("📺 شاهد المزيد من الحلقات", url=more_episodes_link)]
            ])
            await client.send_photo(chat_id=PUBLIC_CHANNEL, photo=poster_id, caption=caption, reply_markup=reply_markup)
            await query.message.edit_text(f"🚀 تم النشر بنجاح بجودة {quality}.")
        except Exception as e:
            await query.message.edit_text(f"⚠️ فشل النشر: {e}")
    else:
        await query.message.edit_text(f"✅ تم الحفظ بجودة {quality}. الرابط:\n{watch_link}")

# ===== 5. تشغيل الفيديو للمستخدمين =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text("أهلاً بك! أرسل رابط الحلقة أو اختر المسلسل لمشاهدة الحلقات.")
        return

    v_id = message.command[1]
    if v_id.startswith("series_"):
        poster_id = v_id.replace("series_", "")
        # جلب كل الحلقات لنفس البوستر
        episodes = db_execute("SELECT ep_num, quality, v_id FROM videos WHERE poster_id = ? ORDER BY ep_num ASC", (poster_id,))
        if not episodes:
            await message.reply_text("❌ لا توجد حلقات لهذا المسلسل حتى الآن.")
            return

        for ep_num, quality, ep_v_id in episodes:
            link = f"https://t.me/{client.me.username}?start={ep_v_id}"
            await message.reply_text(f"🔹 الحلقة {ep_num} | الجودة: {quality}\n▶️ {link}")
    else:
        try:
            await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        except:
            await message.reply_text("❌ عذراً، الحلقة غير متوفرة حالياً.")

app.run()
