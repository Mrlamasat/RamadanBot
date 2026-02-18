import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from PIL import Image, ImageDraw, ImageFont

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedQualityBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

video_memory = {}

def format_duration(seconds):
    if not seconds: return "00:00"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"

# ===== دالة التصميم السينمائي =====
def create_super_poster(base_path, duration_text, quality_text, output="final_animation.gif"):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size
        try:
            font_info = ImageFont.truetype("Cairo-Bold.ttf", int(width * 0.035))
            font_small = ImageFont.truetype("Cairo-Bold.ttf", int(width * 0.025))
        except:
            font_info = font_small = ImageFont.load_default()

        btn_src = Image.open("play_button.png").convert("RGBA")
        btn_w = int(width * 0.20)
        btn_h = int(btn_src.height * (btn_w / btn_src.width))

        frames = []
        scales = [1.0, 1.03, 1.06, 1.03, 1.0, 0.97]

        for scale in scales:
            temp = base.copy()
            draw = ImageDraw.Draw(temp)

            # 1. شريط المعلومات السفلي
            bar_h = int(height * 0.15)
            draw.rectangle([0, height - bar_h, width, height], fill=(0, 0, 0, 220))
            info_text = f"2026  •  جودة {quality_text}  •  🔥 مشاهدة حصرية"
            bbox = draw.textbbox((0, 0), info_text, font=font_info)
            tx = (width - (bbox[2] - bbox[0])) // 2
            draw.text((tx, height - bar_h + int(bar_h * 0.3)), info_text, font=font_info, fill="white")

            # 2. زر التشغيل والنبض
            w_p, h_p = int(btn_w * scale), int(btn_h * scale)
            btn_resized = btn_src.resize((w_p, h_p), Image.LANCZOS)
            btn_x, btn_y = (width - w_p) // 2, (height - h_p) // 2
            temp.paste(btn_resized, (btn_x, btn_y), btn_resized)

            # 3. دائرة المدة (تصميم محمد)
            circle_radius = int(btn_w * 0.28)
            circle_x = width // 2
            circle_y = btn_y + h_p + circle_radius // 2 + 10
            draw.ellipse([circle_x - circle_radius, circle_y - (circle_radius//2),
                         circle_x + circle_radius, circle_y + (circle_radius//2)], fill=(0, 0, 0, 180))
            
            bbox_dur = draw.textbbox((0, 0), duration_text, font=font_small)
            dur_x = circle_x - (bbox_dur[2] - bbox_dur[0]) // 2
            dur_y = circle_y - (bbox_dur[3] - bbox_dur[1]) // 2
            draw.text((dur_x, dur_y), duration_text, font=font_small, fill="white")

            frames.append(temp.convert("RGB"))

        frames[0].save(output, save_all=True, append_images=frames[1:], duration=120, loop=0)
        return output
    except Exception as e:
        logging.error(f"Design error: {e}")
        return base_path

# ===== استقبال الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = 0
    if message.video: duration = message.video.duration
    elif message.document: duration = getattr(message.document, "duration", 0)
    
    video_memory[message.id] = {"duration": format_duration(duration), "status": "waiting"}
    await message.reply_text(f"✅ تم الربط (ID: {message.id})\nأرسل البوستر الآن.")

# ===== استقبال البوستر وإظهار أزرار الجودة =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending = [vid for vid, data in video_memory.items() if data.get("status") == "waiting"]
    if not pending: return
    v_id = pending[-1]
    
    video_memory[v_id]["poster_path"] = await message.download()
    video_memory[v_id]["title"] = message.caption or "حلقة جديدة"
    
    # إظهار أزرار اختيار الجودة
    quality_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
         InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}"),
         InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}")]
    ])
    
    await message.reply_text("📌 اختر جودة العرض ليتم النشر فوراً:", reply_markup=quality_markup)

# ===== معالجة اختيار الجودة والنشر النهائي =====
@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    # تنسيق البيانات: q_QUALITY_VID
    _, quality, v_id = query.data.split("_")
    v_id = int(v_id)
    
    if v_id not in video_memory or video_memory[v_id].get("status") != "waiting":
        await query.answer("⚠️ حدث خطأ أو انتهت صلاحية الطلب.", show_alert=True)
        return

    data = video_memory[v_id]
    await query.message.edit(f"🚀 جاري معالجة ونشر الحلقة بجودة {quality}...")
    
    gif_path = create_super_poster(data["poster_path"], data["duration"], quality)
    
    bot_user = (await client.get_me()).username
    link = f"https://t.me/{bot_user}?start={v_id}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)]])
    
    await client.send_animation(CHANNEL_ID, animation=gif_path, 
                               caption=f"🎬 **{data['title']}**\n\n📥 [اضغط هنا للمشاهدة الآن]({link})", 
                               reply_markup=markup)
    
    video_memory[v_id]["status"] = "posted"
    if os.path.exists(data["poster_path"]): os.remove(data["poster_path"])
    if os.path.exists(gif_path): os.remove(gif_path)
    await query.message.delete()

# ===== نظام الـ Start والاشتراك =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    file_id = message.command[1] if len(message.command) > 1 else None
    if not file_id:
        await message.reply_text("مرحباً بك يا محمد!")
        return
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(file_id))
    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{file_id}")]]
        await message.reply_text("⚠️ اشترك لمشاهدة الحلقة.", reply_markup=InlineKeyboardMarkup(btn))

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id))
    except:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)

app.run()
