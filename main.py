import os
import sqlite3
import logging
import uuid
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant
from PIL import Image

# ================== إعدادات التسجيل ==================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedProBot_Final_v5", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ================== قاعدة البيانات ==================
DB_PATH = "bot_data.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            v_id TEXT,
            duration TEXT,
            title TEXT,
            poster_path TEXT,
            status TEXT DEFAULT 'waiting'
        )
        """)
init_db()

def db_execute(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.fetchall() if fetch else None

# ================== 1. حذف رسائل الانضمام والخدمة (جديد) ==================
@app.on_message(filters.service, group=1)
async def delete_service_messages(client, message: Message):
    try:
        await message.delete()
    except Exception as e:
        logging.error(f"Error deleting service message: {e}")

# ================== 2. تصميم البوستر (تأثير نبض الزر فقط) ==================
def create_animated_poster(base_path):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size
        
        # التأكد من وجود صورة زر التشغيل
        if not os.path.exists("play_button.png"):
            # إنشاء زر مؤقت لو لم ترفعه أنت
            btn_src = Image.new("RGBA", (200, 200), (255, 255, 255, 100))
        else:
            btn_src = Image.open("play_button.png").convert("RGBA")

        btn_w = int(width * 0.22)
        btn_h = int(btn_src.height * (btn_w / btn_src.width))
        
        output = f"tmp_{uuid.uuid4().hex}.gif"
        frames = []
        # حركات النبض (Scale)
        for scale in [1.0, 1.05, 1.0]:
            temp = base.copy()
            w_p, h_p = int(btn_w*scale), int(btn_h*scale)
            btn_resized = btn_src.resize((w_p, h_p), Image.LANCZOS)
            temp.paste(btn_resized, ((width-w_p)//2, (height-h_p)//2), btn_resized)
            frames.append(temp.convert("RGB"))

        frames[0].save(output, save_all=True, append_images=frames[1:], duration=200, loop=0)
        return output
    except Exception as e:
        logging.error(f"Design Error: {e}")
        return base_path

# ================== 3. معالجة القناة (الفيديو ثم البوستر) ==================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def video_handler(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    mins, secs = divmod(duration, 60)
    d_text = f"{mins}:{secs:02d} دقيقة"
    
    db_execute("INSERT INTO videos (v_id, duration) VALUES (?, ?)", (str(message.id), d_text))
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\nالآن أرسل البوستر كصورة.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def photo_handler(client, message):
    res = db_execute("SELECT id FROM videos WHERE status='waiting' ORDER BY id DESC LIMIT 1", fetch=True)
    if not res: return
    
    db_id = res[0][0]
    path = await message.download()
    db_execute("UPDATE videos SET poster_path=?, title=? WHERE id=?", (path, message.caption or "حلقة جديدة", db_id))
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("4K", callback_data=f"q_4K_{db_id}"),
         InlineKeyboardButton("HD", callback_data=f"q_HD_{db_id}"),
         InlineKeyboardButton("SD", callback_data=f"q_SD_{db_id}")]
    ])
    await message.reply_text("📌 اختر الجودة للنشر:", reply_markup=markup)

# ================== 4. النشر النهائي بالتنسيق المطلوب ==================
@app.on_callback_query(filters.regex(r"^q_"))
async def publish_handler(client, query):
    _, quality, db_id = query.data.split("_")
    res = db_execute("SELECT v_id, duration, title, poster_path FROM videos WHERE id=?", (db_id,), fetch=True)
    if not res or not res[0][3]: return
    
    v_id, duration, title, poster_path = res[0]
    gif_path = create_animated_poster(poster_path)
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    # التنسيق المطلوب: خط عادي تحت العنوان
    caption = (
        f"🎬 **{title}**\n"
        f"⏱ المدة: {duration}\n"
        f"🌟 الجودة: {quality}\n\n"
        f"📥 [اضغط هنا للمشاهدة الآن]({link})"
    )
    
    await client.send_animation(
        CHANNEL_ID,
        animation=gif_path,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]])
    )
    
    db_execute("UPDATE videos SET status='posted' WHERE id=?", (db_id,))
    
    # تنظيف الملفات (هام جداً لـ Railway)
    if os.path.exists(poster_path): os.remove(poster_path)
    if os.path.exists(gif_path): os.remove(gif_path)
    await query.message.delete()

# ================== 5. نظام Start والتحقق ==================
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        try:
            await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
            await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id))
        except UserNotParticipant:
            btn = [[InlineKeyboardButton("📢 اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")],
                   [InlineKeyboardButton("✅ تم الاشتراك - شاهد الآن", callback_data=f"chk_{v_id}")]]
            await message.reply_text("⚠️ يجب الاشتراك في القناة لتفعيل روابط المشاهدة.", reply_markup=InlineKeyboardMarkup(btn))
        except Exception as e:
            await message.reply_text(f"❌ حدث خطأ: {e}")
    else:
        await message.reply_text(f"أهلاً بك يا محمد! البوت جاهز للعمل.")

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id))
    except:
        await query.answer("⚠️ لم تشترك بعد في القناة!", show_alert=True)

if __name__ == "__main__":
    app.run()
