import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from PIL import Image, ImageDraw, ImageFont

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات من البيئة =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSpeedBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

video_memory = {}

# ===== دالة تحويل الثواني إلى وقت (00:00) =====
def format_duration(seconds):
    if not seconds: return "مشاهدة ممتعة"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d} دقيقة"

# ===== دالة صنع البوستر النظيف بالنبض والمدة =====
def create_pulsing_poster(base_path, duration_text, output="final_animation.gif"):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size
        
        try:
            font_info = ImageFont.truetype("Cairo-Bold.ttf", int(width * 0.04))
        except:
            font_info = ImageFont.load_default()

        # إعداد الزر الأحمر السادة
        btn_src = Image.open("play_button.png").convert("RGBA")
        red_color = (229, 9, 20)
        btn_ch = btn_src.split()
        red_btn = Image.merge("RGBA", (
            Image.new("L", btn_src.size, red_color[0]),
            Image.new("L", btn_src.size, red_color[1]),
            Image.new("L", btn_src.size, red_color[2]),
            btn_ch[3]
        ))
        
        btn_w = int(width * 0.20)
        btn_h = int(red_btn.height * (btn_w / red_btn.width))
        
        frames = []
        # مستويات النبض (تغيير الحجم)
        scales = [1.0, 1.03, 1.06, 1.03, 1.0, 0.97]

        for scale in scales:
            temp = base.copy()
            draw = ImageDraw.Draw(temp)
            
            # شريط المعلومات السفلي (بدون توهج)
            bar_h = int(height * 0.12)
            draw.rectangle([0, height - bar_h, width, height], fill=(0, 0, 0, 220))
            
            info_text = f"2026  •  {duration_text}  •  1080p  •  🔥 حصري"
            bbox = draw.textbbox((0, 0), info_text, font=font_info)
            tx = (width - (bbox[2] - bbox[0])) // 2
            draw.text((tx, height - bar_h + (bar_h // 3)), info_text, font=font_info, fill="white")

            # رسم الزر النابض
            w_p, h_p = int(btn_w * scale), int(btn_h * scale)
            btn_resized = red_btn.resize((w_p, h_p), Image.LANCZOS)
            temp.paste(btn_resized, ((width - w_p)//2, (height - h_p)//2), btn_resized)
            
            frames.append(temp.convert("RGB"))

        frames[0].save(output, save_all=True, append_images=frames[1:], duration=120, loop=0)
        return output
    except Exception as e:
        logging.error(f"Design error: {e}")
        return base_path

# ===== استقبال الفيديو (جلب البيانات مباشرة من تليجرام) =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    # هنا السر: تليجرام يرسل المدة جاهزة في metadata الفيديو
    duration_seconds = 0
    if message.video:
        duration_seconds = message.video.duration
    elif message.document and message.document.mime_type.startswith("video"):
        # في حال كان ملف فيديو، قد لا تتوفر المدة مباشرة
        duration_seconds = 0 

    duration_text = format_duration(duration_seconds)
    
    video_memory[message.id] = {"duration": duration_text, "status": "waiting"}
    await message.reply_text(f"✅ تم ربط الفيديو بنجاح.\n⏱ المدة المكتشفة: {duration_text}\nارفع البوستر الآن مع العنوان في الـ Caption.")

# ===== استقبال البوستر والنشر النهائي =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending = [vid for vid, data in video_memory.items() if data.get("status") == "waiting"]
    if not pending: return
    v_id = pending[-1]
    
    t_msg = await message.reply_text("⏳ جاري إنتاج البوستر النابض...")
    path = await message.download()
    
    # صنع الـ GIF
    gif_path = create_pulsing_poster(path, video_memory[v_id]["duration"])
    
    bot_me = await client.get_me()
    link = f"https://t.me/{bot_me.username}?start={v_id}"
    
    # أزرار النشر
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)],
        [InlineKeyboardButton("📝 تعديل العنوان", callback_data=f"edit_{v_id}")]
    ])
    
    await client.send_animation(
        chat_id=CHANNEL_ID,
        animation=gif_path,
        caption=f"🎬 **{message.caption or 'حلقة جديدة'}**\n\n📥 [اضغط هنا للمشاهدة]({link})",
        reply_markup=markup
    )
    
    video_memory[v_id]["status"] = "posted"
    await t_msg.delete()
    if os.path.exists(path): os.remove(path)
    if os.path.exists(gif_path): os.remove(gif_path)

# ===== باقي الوظائف (الاشتراك وتعديل العنوان) تظل كما هي في كودك السابق =====
# ... (يمكنك دمج دالة start و edit_title من الكود السابق هنا)

app.run()
