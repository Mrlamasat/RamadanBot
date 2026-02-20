import os
import sqlite3
import logging
import uuid
from datetime import timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant

# ===== الإعدادات =====
logging.basicConfig(level=logging.INFO)
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def db_query(q, p=(), fetch=True):
    with sqlite3.connect("bot_data.db") as conn:
        cur = conn.execute(q, p)
        if fetch: return cur.fetchall()
        conn.commit()

def init_db():
    db_query("""CREATE TABLE IF NOT EXISTS videos 
                (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                 poster_id TEXT, status TEXT, ep_num INTEGER, series_tag TEXT)""", fetch=False)
    db_query("""CREATE TABLE IF NOT EXISTS subscriptions 
                (user_id INTEGER, series_tag TEXT, UNIQUE(user_id, series_tag))""", fetch=False)
init_db()

current_upload = {}

# =========================
# 1️⃣ استلام الفيديو
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = str(timedelta(seconds=duration_sec)) if duration_sec else "غير معروف"
    
    current_upload.clear()
    current_upload.update({"v_id": str(message.id), "duration": duration})
    
    await message.reply_text(f"✅ تم استلام الفيديو\n⏱ المدة: {duration}\n🖼 **أرسل البوستر الآن:**", quote=True)

# =========================
# 2️⃣ استلام البوستر + العنوان الاختياري
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    if "v_id" not in current_upload: return
    
    current_upload.update({
        "poster": message.photo.file_id,
        "series_tag": str(uuid.uuid4())[:8],
        "default_title": message.caption or "حلقة جديدة"
    })
    
    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ استخدام وصف الصورة", callback_data="set_title_old")],
        [InlineKeyboardButton("✏️ كتابة عنوان جديد", callback_data="set_title_new")]
    ])
    await message.reply_text("🖼 تم حفظ البوستر. كيف تود وضع العنوان؟", reply_markup=btns, quote=True)

@app.on_callback_query(filters.regex("^set_title_"))
async def title_choice(client, query):
    if query.data.endswith("old"):
        current_upload["title"] = current_upload["default_title"]
        await query.message.edit_text(f"📝 العنوان: {current_upload['title']}\n🔢 **أرسل رقم الحلقة الآن:**")
    else:
        current_upload["wait_title"] = True
        await query.message.edit_text("📝 **أرسل العنوان الجديد الآن:**")

# =========================
# 3️⃣ استلام النص (عنوان أو رقم)
# =========================
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def handle_text(client, message):
    if current_upload.get("wait_title"):
        current_upload.update({"title": message.text, "wait_title": False})
        await message.reply_text(f"✅ تم اعتماد العنوان: {message.text}\n🔢 **أرسل رقم الحلقة:**", quote=True)
        return

    if "poster" in current_upload and message.text.isdigit():
        current_upload["ep"] = int(message.text)
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("HD", callback_data="pub_HD"),
             InlineKeyboardButton("SD", callback_data="pub_SD"),
             InlineKeyboardButton("4K", callback_data="pub_4K")]
        ])
        await message.reply_text("✨ اختر الجودة للنشر النهائي:", reply_markup=btns, quote=True)

# =========================
# 4️⃣ النشر الفعلي والإشعارات
# =========================
@app.on_callback_query(filters.regex("^pub_"))
async def finalize(client, query):
    quality = query.data.split("_")[1]
    v_id, poster, ep, dur, tag, title = (current_upload.get(k) for k in ["v_id", "poster", "ep", "duration", "series_tag", "title"])
    
    db_query("INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?, ?)", (v_id, dur, title, poster, "posted", ep, tag), fetch=False)
    
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = f"🎬 **{title}**\n🔹 الحلقة: {ep}\n✨ الجودة: {quality}\n⏱ المدة: {dur}\n\n📥 [مشاهدة الآن]({link})"
    
    # النشر في القناة العامة
    await client.send_photo(PUBLIC_CHANNEL, photo=poster, caption=caption, 
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    # إرسال إشعارات للمشتركين السابقين في هذا المسلسل
    subs = db_query("SELECT user_id FROM subscriptions WHERE series_tag = ?", (tag,))
    for sub_id in subs:
        try: await client.send_message(sub_id[0], f"🔔 حلقة جديدة من **{title}** جُهزت!\n📥 [اضغط للمشاهدة]({link})")
        except: pass
        
    await query.message.edit_text("🚀 تم النشر وإرسال الإشعارات!")
    current_upload.clear()

# =========================
# 5️⃣ نظام Start والاشتراك الإجباري
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text("أهلاً بك يا محمد! أرسل الرابط للمشاهدة.")
        return

    v_id = message.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        
        # إرسال الفيديو
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        
        # جلب بيانات المسلسل لعرض الحلقات وتسجيل الاشتراك
        data = db_query("SELECT series_tag, title FROM videos WHERE v_id = ?", (v_id,))
        if data:
            tag, title = data[0]
            db_query("INSERT OR IGNORE INTO subscriptions VALUES (?, ?)", (message.from_user.id, tag), fetch=False)
            
            all_eps = db_query("SELECT v_id, ep_num FROM videos WHERE series_tag = ? ORDER BY ep_num ASC", (tag,))
            if len(all_eps) > 1:
                btns = []
                row = []
                for vid, num in all_eps:
                    label = f"▶️ {num}" if vid == v_id else f"{num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                    if len(row) == 4: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text(f"📺 حلقات مسلسل **{title}**:", reply_markup=InlineKeyboardMarkup(btns))
                
    except UserNotParticipant:
        await message.reply_text(f"⚠️ اشترك أولاً في @{PUBLIC_CHANNEL} لتفعيل الرابط.", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك الآن", url=f"https://t.me/{PUBLIC_CHANNEL}")]]))

app.run()
