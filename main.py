import os
import asyncio
import logging
import uuid
import asyncpg
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from PIL import Image, ImageDraw, ImageFont

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية (تعديل السطر 8 وما حوله ليكون آمناً) =====
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app = Client("MohammedPro_Ultimate", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_pool = None

# ===== تهيئة PostgreSQL =====
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                v_id TEXT PRIMARY KEY,
                duration TEXT,
                title TEXT,
                poster_path TEXT,
                status TEXT,
                user_id BIGINT
            );
        """)
    print("✅ قاعدة بيانات Postgres متصلة وجاهزة.")

# ===== دوال التصميم والمساعدة =====
def format_duration(seconds):
    if not seconds: return "00:00"
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}:{secs:02d} دقيقة"

def create_super_poster(base_path, duration_text, quality_text):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size
        try:
            font = ImageFont.truetype("Cairo-Bold.ttf", int(width * 0.045))
        except:
            font = ImageFont.load_default()

        # زر التشغيل (يجب رفعه للمجلد الرئيسي)
        btn_src = Image.open("play_button.png").convert("RGBA")
        btn_w = int(width * 0.25)
        btn_h = int(btn_src.height * (btn_w / btn_src.width))

        output = f"poster_{uuid.uuid4().hex}.gif"
        frames = []
        scales = [1.0, 1.05, 1.1, 1.05, 1.0] # حركة النبض

        for scale in scales:
            temp = base.copy()
            draw = ImageDraw.Draw(temp)
            bar_h = int(height * 0.15)
            draw.rectangle([0, height - bar_h, width, height], fill=(0, 0, 0, 220))
            
            info = f"{duration_text} • {quality_text} • 2026"
            bbox = draw.textbbox((0, 0), info, font=font)
            tx = (width - (bbox[2] - bbox[0])) // 2
            draw.text((tx, height - bar_h + int(bar_h * 0.3)), info, font=font, fill="white")

            w_p, h_p = int(btn_w * scale), int(btn_h * scale)
            btn_res = btn_src.resize((w_p, h_p), Image.LANCZOS)
            temp.paste(btn_res, ((width - w_p) // 2, (height - h_p) // 2), btn_res)
            frames.append(temp.convert("RGB"))

        frames[0].save(output, save_all=True, append_images=frames[1:], duration=150, loop=0)
        return output
    except Exception as e:
        logging.error(f"Design Error: {e}")
        return base_path

# ===== معالجة القناة والمستخدمين =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def channel_video_handler(client, m):
    duration = m.video.duration if m.video else getattr(m.document, "duration", 0)
    d_text = format_duration(duration)
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO videos (v_id, duration, status) VALUES ($1, $2, $3) ON CONFLICT (v_id) DO NOTHING", str(m.id), d_text, "waiting")
    await m.reply_text(f"✅ تم ربط الفيديو (ID: {m.id})\nأرسل الآن البوستر كصورة مع العنوان في الوصف.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def channel_photo_handler(client, m):
    async with db_pool.acquire() as conn:
        v_id = await conn.fetchval("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
        if not v_id: return
        path = await m.download()
        title = m.caption or "حلقة جديدة"
        await conn.execute("UPDATE videos SET poster_path=$1, title=$2 WHERE v_id=$3", path, title, v_id)
        
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}")]])
    await m.reply_text(f"📌 بوستر جاهز للفيديو {v_id}. اختر الجودة للنشر:", reply_markup=markup)

@app.on_callback_query(filters.regex(r"^q_"))
async def post_final(client, q):
    _, quality, v_id = q.data.split("_")
    async with db_pool.acquire() as conn:
        res = await conn.fetchrow("SELECT * FROM videos WHERE v_id=$1", v_id)
        if not res: return
        
    gif = create_super_poster(res['poster_path'], res['duration'], quality)
    bot = await client.get_me()
    link = f"https://t.me/{bot.username}?start={v_id}"
    
    await client.send_animation(CHANNEL_ID, animation=gif, caption=f"🎬 **{res['title']}**\n\n📥 [شاهد الآن بالضغط هنا]({link})", 
                               reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)]]))
    
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE videos SET status='posted' WHERE v_id=$1", v_id)
    if os.path.exists(res['poster_path']): os.remove(res['poster_path'])
    if os.path.exists(gif): os.remove(gif)
    await q.message.delete()

@app.on_message(filters.command("start") & filters.private)
async def start(client, m):
    if len(m.command) < 2:
        return await m.reply_text("أهلاً بك يا محمد! البوت يعمل بنظام Postgres المتطور.")
    
    v_id = m.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, m.from_user.id)
        await client.copy_message(m.chat.id, CHANNEL_ID, int(v_id))
    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")]]
        await m.reply_text("⚠️ اشترك في القناة لمشاهدة الحلقة.", reply_markup=InlineKeyboardMarkup(btn))

async def main():
    await init_db()
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
