import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

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
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    # أضفنا عمود quality لتخزين الجودة المختارة
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, title TEXT, 
                       poster_id TEXT, status TEXT, ep_num INTEGER, quality TEXT)''')
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=True):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    res = cursor.fetchall() if fetch else None
    conn.close()
    return res

# 1. استقبال الفيديو من قناة التخزين
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    db_execute("INSERT OR REPLACE INTO videos (v_id, status) VALUES (?, ?)", (v_id, "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\n🖼 الآن أرسل البوستر (صورة فقط):")

# 2. استقبال البوستر (بدون وصف)
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    # البوستر هنا لا يحتاج لوصف، سيتم الانتقال لطلب رقم الحلقة فوراً
    db_execute("UPDATE videos SET poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"🖼 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة فقط:")

# 3. استقبال رقم الحلقة وعرض أزرار الجودة
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    if not message.text.isdigit(): return
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    
    v_id = res[0]
    ep_num = int(message.text)
    db_execute("UPDATE videos SET ep_num = ?, status = 'awaiting_quality' WHERE v_id = ?", (ep_num, v_id), fetch=False)
    
    # أزرار اختيار الجودة
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 HD", callback_data=f"setq_HD_{v_id}"),
            InlineKeyboardButton("📺 SD", callback_data=f"setq_SD_{v_id}")
        ]
    ])
    await message.reply_text(f"✅ تم تحديد الحلقة {ep_num}.\n✨ اختر الجودة المطلوبة للنشر:", reply_markup=btns)

# 4. معالجة اختيار الجودة والنشر التلقائي
@app.on_callback_query(filters.regex(r"^setq_"))
async def publish_handler(client, query: CallbackQuery):
    data = query.data.split("_")
    quality = data[1]
    v_id = data[2]
    
    res = db_execute("SELECT ep_num, poster_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    ep_num, poster_id = res[0]
    
    db_execute("UPDATE videos SET quality = ?, status = 'posted' WHERE v_id = ?", (quality, v_id), fetch=False)
    
    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    if PUBLIC_CHANNEL:
        try:
            caption = f"🎬 **حلقة جديدة**\n🔹 **رقم الحلقة:** {ep_num}\n✨ **الجودة:** {quality}\n\n📥 **لمشاهدة الحلقة اضغط على الزر أدناه:**"
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
            await client.send_photo(chat_id=PUBLIC_CHANNEL, photo=poster_id, caption=caption, reply_markup=reply_markup)
            await query.message.edit_text(f"🚀 تم النشر بنجاح بجودة {quality} في @{PUBLIC_CHANNEL}")
        except Exception as e:
            await query.message.edit_text(f"⚠️ فشل النشر: {e}")
    else:
        await query.message.edit_text(f"✅ تم الحفظ بجودة {quality}. الرابط:\n{watch_link}")

# 5. نظام التشغيل (Start)
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد! أرسل رابط الحلقة للمشاهدة.")
        return

    v_id = message.command[1]
    try:
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await message.reply_text("❌ عذراً، الحلقة غير متوفرة حالياً.")

app.run()
