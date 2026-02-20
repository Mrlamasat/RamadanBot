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
def db_execute(q, p=(), fetch=True):
    with sqlite3.connect("bot.db") as conn:
        cur = conn.execute(q, p)
        if fetch: return cur.fetchall()
        conn.commit()

def init_db():
    db_execute("""
    CREATE TABLE IF NOT EXISTS videos (
        v_id TEXT PRIMARY KEY,
        poster_id TEXT,
        ep_num INTEGER,
        quality TEXT,
        duration TEXT,
        status TEXT
    )
    """, fetch=False)

init_db()

# =========================
# 1️⃣ استقبال الفيديو
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    
    # استخراج المدة
    duration_sec = 0
    if message.video: duration_sec = message.video.duration
    elif message.document and hasattr(message.document, "duration"): duration_sec = message.document.duration
    
    duration = str(timedelta(seconds=duration_sec)) if duration_sec else "غير معروف"

    # حفظ بوضع 'WAITING_POSTER'
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (v_id, duration, "WAITING_POSTER"), fetch=False)
    
    await message.reply_text(f"✅ تم استلام الفيديو.\n⏱ المدة: {duration}\n🖼 **الآن أرسل البوستر لهذه الحلقة حصراً:**", quote=True)

# =========================
# 2️⃣ استقبال البوستر
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    # نبحث عن آخر فيديو لم يتم رفع بوستر له
    res = db_execute("SELECT v_id FROM videos WHERE status='WAITING_POSTER' ORDER BY rowid DESC LIMIT 1")
    if not res:
        await message.reply_text("⚠️ لا يوجد فيديو ينتظر بوستر. ارفع الفيديو أولاً.")
        return

    v_id = res[0][0]
    db_execute("UPDATE videos SET poster_id=?, status='WAITING_EP' WHERE v_id=?", 
               (message.photo.file_id, v_id), fetch=False)
    
    await message.reply_text(f"🖼 تم حفظ البوستر للفيديو {v_id}.\n🔢 **أرسل الآن رقم الحلقة:**", quote=True)

# =========================
# 3️⃣ استقبال رقم الحلقة
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep(client, message):
    if not message.text.isdigit(): return

    # نبحث عن فيديو ينتظر الرقم
    res = db_execute("SELECT v_id FROM videos WHERE status='WAITING_EP' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num=?, status='WAITING_QUALITY' WHERE v_id=?", 
               (int(message.text), v_id), fetch=False)

    # إنشاء الأزرار مع ربط الـ v_id بالـ Callback لضمان عدم التجاهل
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 HD", callback_data=f"set_{v_id}_HD"),
            InlineKeyboardButton("📺 SD", callback_data=f"set_{v_id}_SD")
        ]
    ])
    
    await message.reply_text(f"🔢 تم تسجيل الحلقة {message.text}.\n⚠️ **لابد من اختيار الجودة الآن للنشر:**", reply_markup=buttons, quote=True)

# =========================
# 4️⃣ معالجة اختيار الجودة (هنا يتم النشر الفعلي)
# =========================
@app.on_callback_query(filters.regex(r"^set_"))
async def finalize_publish(client, query: CallbackQuery):
    # تفكيك البيانات: set_id_quality
    parts = query.data.split("_")
    v_id = parts[1]
    quality = parts[2]
    
    res = db_execute("SELECT ep_num, poster_id, duration, status FROM videos WHERE v_id=?", (v_id,))
    if not res or res[0][3] == "POSTED":
        await query.answer("⚠️ هذا الطلب تم معالجته مسبقاً.")
        return
    
    ep_num, poster_id, duration, _ = res[0]
    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"

    caption = (f"🎬 **الحلقة {ep_num}**\n"
               f"✨ **الجودة:** {quality}\n"
               f"⏱ **المدة:** {duration}\n\n"
               f"📥 لمشاهدة الحلقة اضغط على الزر أدناه:")

    try:
        # النشر في القناة العامة
        await client.send_photo(
            chat_id=PUBLIC_CHANNEL,
            photo=poster_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ تشغيل الحلقة", url=watch_link)]])
        )
        
        # تحديث القاعدة لمنع تكرار النشر
        db_execute("UPDATE videos SET quality=?, status='POSTED' WHERE v_id=?", (quality, v_id), fetch=False)
        
        await query.message.edit_text(f"🚀 تم النشر بنجاح بجودة {quality}!")
        await query.answer("تم النشر بنجاح ✅")
    except Exception as e:
        await query.answer(f"❌ خطأ: {e}", show_alert=True)

# =========================
# 5️⃣ نظام التشغيل (Start)
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        try:
            await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        except:
            await message.reply_text("❌ الحلقة غير متوفرة.")
    else:
        await message.reply_text("أهلاً بك يا محمد!")

app.run()
