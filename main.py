import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from PIL import Image

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSuperBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_path TEXT, poster_id TEXT, status TEXT)''')
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

# ===== دوال التصميم (نبض زر التشغيل) =====
def create_super_poster(base_path, output="final_animation.gif"):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size
        btn_src = Image.open("play_button.png").convert("RGBA")
        btn_w = int(width * 0.22)
        btn_h = int(btn_src.height * (btn_w / btn_src.width))
        frames = []
        scales = [1.0, 1.05, 1.1, 1.05, 1.0]
        for scale in scales:
            temp = base.copy()
            w_p, h_p = int(btn_w * scale), int(btn_h * scale)
            btn_resized = btn_src.resize((w_p, h_p), Image.Resampling.LANCZOS)
            temp.paste(btn_resized, ((width - w_p)//2, (height - h_p)//2), btn_resized)
            frames.append(temp.convert("P", palette=Image.Palette.ADAPTIVE))
        frames[0].save(output, save_all=True, append_images=frames[1:], duration=150, loop=0, optimize=False)
        return output
    except Exception as e:
        logging.error(f"Design error: {e}")
        return base_path

# ===== استقبال الميديا (قناة الرفع) =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    mins, secs = divmod(duration, 60)
    dur_text = f"{mins}:{secs:02d} دقيقة"
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (str(message.id), dur_text, "waiting"), fetch=False)
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\nأرسل البوستر الآن كصورة.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    path = await message.download()
    title = message.caption or "حلقة جديدة"
    db_execute("UPDATE videos SET poster_path = ?, title = ?, poster_id = ? WHERE v_id = ?", 
               (path, title, message.photo.file_unique_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
                                    InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}"),
                                    InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}")]])
    await message.reply_text(f"📌 تم الربط: {title}\nاختر الجودة للنشر:", reply_markup=markup)

# ===== النشر النهائي للنظام =====
@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_path FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, poster_path = res[0]
    
    await query.message.edit("🚀 جاري معالجة البوستر ونشر الحلقة...")
    gif_path = create_super_poster(poster_path)
    bot_username = (await client.get_me()).username
    link = f"https://t.me/{bot_username}?start={v_id}"
    
    caption_text = (
        f"🎬 **{title}**\n\n"
        f"⏱ المـدة: {duration}\n"
        f"✨ الجـودة: {quality}\n"
        f"🗓 سـنة العرض: 2026\n\n"
        f"📥 [اضغط هنا للمشاهدة الآن]({link})\n"
        f"━━━━━━━━━━━━━━"
    )
    
    await client.send_animation(
        CHANNEL_ID, 
        animation=gif_path, 
        caption=caption_text, 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)]])
    )
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
    if os.path.exists(poster_path): os.remove(poster_path)
    if os.path.exists(gif_path): os.remove(gif_path)
    await query.message.delete()

# ===== نظام الـ Start (يدعم القديم والجديد) =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد! 🎬\nاستخدم الروابط لمشاهدة الحلقات.")
        return

    v_id = message.command[1]
    
    try:
        # 1. التحقق من الاشتراك الإجباري
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        
        # 2. إرسال الفيديو مباشرة (يعمل مع الفيديوهات القديمة والجديدة)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id))
        
        # 3. محاولة جلب باقي الحلقات (للمسجلات في القاعدة فقط)
        video_data = db_execute("SELECT poster_id, title FROM videos WHERE v_id = ?", (v_id,))
        if video_data:
            poster_id, title = video_data[0]
            all_ep = db_execute("SELECT v_id FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY v_id ASC", (poster_id,))
            if len(all_ep) > 1:
                btns = []
                row = []
                bot_username = (await client.get_me()).username
                for i, ep in enumerate(all_ep, 1):
                    row.append(InlineKeyboardButton(f"الحلقة {i}", url=f"https://t.me/{bot_username}?start={ep[0]}"))
                    if len(row) == 2:
                        btns.append(row)
                        row = []
                if row: btns.append(row)
                await message.reply_text(f"📺 **باقي حلقات مسلسل {title}:**", reply_markup=InlineKeyboardMarkup(btns))

    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك بالقناة لتفعيل روابط المشاهدة.", reply_markup=InlineKeyboardMarkup(btn))
    except Exception as e:
        logging.error(f"Start Error: {e}")
        await message.reply_text("❌ عذراً، هذا الفيديو غير متاح حالياً.")

# ===== التحقق من الاشتراك بعد الضغط على الزر =====
@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id))
        # ملاحظة: الفيديوهات القديمة لن تظهر تحتها أزرار الحلقات عند الضغط على "تم الاشتراك"
    except:
        await query.answer("⚠️ اشترك أولاً في القناة!", show_alert=True)

app.run()
