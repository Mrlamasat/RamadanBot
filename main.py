import os
import sqlite3
import logging
import uuid
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from PIL import Image, ImageDraw, ImageFont

# ===== إعدادات التسجيل لمراقبة العمليات =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
# تأكد من تحديث هذا التوكن في إعدادات Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "-1003547072209") 
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedProBot_Final_v3", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إعداد قاعدة البيانات SQLite =====
DB_PATH = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            duration TEXT,
            title TEXT,
            poster_path TEXT,
            status TEXT,
            user_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=False):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        if fetch:
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"SQLite Error: {e}")
        return []
    finally:
        conn.close()

# ===== دوال المساعدة والتصميم =====
def format_duration(seconds):
    if not seconds: return "00:00"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d} دقيقة"

def create_super_poster(base_path, duration_text, quality_text, output=None):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size
        try:
            font_info = ImageFont.truetype("Cairo-Bold.ttf", int(width * 0.040))
        except:
            font_info = ImageFont.load_default()

        btn_src = Image.open("play_button.png").convert("RGBA")
        btn_w = int(width * 0.22)
        btn_h = int(btn_src.height * (btn_w / btn_src.width))

        output = output or f"tmp_{uuid.uuid4().hex}.gif"
        frames = []
        scales = [1.0, 1.03, 1.06, 1.03, 1.0, 0.97]

        for scale in scales:
            temp = base.copy()
            draw = ImageDraw.Draw(temp)
            bar_h = int(height * 0.14)
            draw.rectangle([0, height - bar_h, width, height], fill=(0, 0, 0, 230))
            
            info_text = f"{duration_text}  •  {quality_text}  •  2026  •  🔥"
            bbox = draw.textbbox((0,0), info_text, font=font_info)
            tx = (width - (bbox[2]-bbox[0]))//2
            draw.text((tx, height - bar_h + int(bar_h*0.28)), info_text, font=font_info, fill="white")

            w_p, h_p = int(btn_w*scale), int(btn_h*scale)
            btn_resized = btn_src.resize((w_p, h_p), Image.LANCZOS)
            temp.paste(btn_resized, ((width-w_p)//2, (height-h_p)//2), btn_resized)
            frames.append(temp.convert("RGB"))

        frames[0].save(output, save_all=True, append_images=frames[1:], duration=120, loop=0)
        return output
    except Exception as e:
        logging.error(f"Design Error: {e}")
        return base_path

# ===== نظام معالجة الرسائل في القناة =====
@app.on_message(filters.chat(int(CHANNEL_ID)))
async def channel_handler(client, message):
    logging.info(f"ميديا جديدة من القناة: ID={message.id}, النوع={message.media}")

    # استقبال الفيديوهات (سواء فيديو أو مستند فيديو)
    if message.video or (message.document and "video" in (message.document.mime_type or "")):
        duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
        d_text = format_duration(duration)
        
        db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status, user_id) VALUES (?, ?, ?, ?)",
                   (str(message.id), d_text, "waiting", message.from_user.id if message.from_user else 0))
        
        await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\nالآن أرسل البوستر كصورة.")

    # استقبال البوستر (صورة)
    elif message.photo:
        res = db_execute("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1", fetch=True)
        if not res: return
        
        v_id = res[0][0]
        path = await message.download()
        title = message.caption or "حلقة جديدة"
        
        db_execute("UPDATE videos SET poster_path=?, title=? WHERE v_id=?", (path, title, v_id))
        
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
             InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}"),
             InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}")]
        ])
        await message.reply_text(f"📌 تم استلام بوستر للفيديو {v_id}\nاختر الجودة للنشر الفوري:", reply_markup=markup)

# ===== معالجة النشر النهائي =====
@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_path FROM videos WHERE v_id=? AND status='waiting'", (v_id,), fetch=True)
    if not res:
        await query.answer("⚠️ طلب غير صالح.", show_alert=True)
        return
        
    duration, title, poster_path = res[0]
    await query.message.edit(f"🚀 جاري معالجة ونشر البوستر ({quality})...")
    
    gif_path = create_super_poster(poster_path, duration, quality)
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    await client.send_animation(int(CHANNEL_ID), animation=gif_path, 
                               caption=f"🎬 **{title}**\n\n📥 [اضغط هنا للمشاهدة الآن]({link})", 
                               reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status='posted' WHERE v_id=?", (v_id,))
    if os.path.exists(poster_path): os.remove(poster_path)
    if os.path.exists(gif_path): os.remove(gif_path)
    await query.message.delete()

# ===== نظام الـ Start للمستخدمين =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد! البوت يعمل بالتوكن الجديد بنجاح.")
        return
    
    v_id = message.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        await client.copy_message(message.chat.id, int(CHANNEL_ID), int(v_id))
    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك - شاهد الآن", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ يجب الاشتراك في القناة لتفعيل روابط المشاهدة.", reply_markup=InlineKeyboardMarkup(btn))
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, int(CHANNEL_ID), int(v_id))
    except:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)

app.run()
