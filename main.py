import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip # مكتبة جلب المدة

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedDurationBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

video_memory = {}

# ===== دالة تحويل الثواني إلى تنسيق وقت (00:00) =====
def format_duration(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d} دقيقة"

# ===== دالة صنع البوستر مع المدة التلقائية =====
def create_pulsing_poster(base_path, title, duration_str, output="final_animation.gif"):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size

        try:
            font_info = ImageFont.truetype("Cairo-Bold.ttf", int(width * 0.035))
        except:
            font_info = ImageFont.load_default()

        # تجهيز الزر الأحمر
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
        scale_values = [1, 1.02, 1.05, 1.02, 1, 0.98] # حركة نبض بسيطة

        for scale in scale_values:
            temp = base.copy()
            draw = ImageDraw.Draw(temp)
            
            # إضافة شريط المعلومات السفلي
            bar_h = int(height * 0.12)
            draw.rectangle([0, height - bar_h, width, height], fill=(0, 0, 0, 220))
            
            # النص يحتوي على المدة التي جلبناها تلقائياً
            info_text = f"2026  •  {duration_str}  •  1080p  •  🔥 حصري"
            
            bbox = draw.textbbox((0, 0), info_text, font=font_info)
            tx = (width - (bbox[2] - bbox[0])) // 2
            draw.text((tx, height - bar_h + (bar_h // 3)), info_text, font=font_info, fill="white")

            # الزر النابض
            w_p, h_p = int(btn_w * scale), int(btn_h * scale)
            btn_resized = red_btn.resize((w_p, h_p), Image.LANCZOS)
            temp.paste(btn_resized, ((width - w_p)//2, (height - h_p)//2), btn_resized)
            
            frames.append(temp.convert("RGB"))

        frames[0].save(output, save_all=True, append_images=frames[1:], duration=150, loop=0)
        return output
    except Exception as e:
        logging.error(f"Error: {e}")
        return base_path

# ===== استقبال الفيديو وجلب مدته =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    msg = await message.reply_text("⏳ جاري فحص الفيديو وجلب المدة...")
    
    try:
        # تحميل جزء بسيط من الفيديو لمعرفة المدة (لسرعة Railway)
        file_path = await message.download()
        clip = VideoFileClip(file_path)
        duration_text = format_duration(clip.duration)
        clip.close()
        os.remove(file_path) # حذف الفيديو فوراً لتوفير المساحة

        video_memory[message.id] = {"duration": duration_text, "status": "waiting"}
        await msg.edit(f"✅ تم حفظ المدة: {duration_text}\nالآن أرسل البوستر واكتب العنوان.")
    except Exception as e:
        video_memory[message.id] = {"duration": "مشاهدة ممتعة", "status": "waiting"}
        await msg.edit("⚠️ لم أتمكن من جلب المدة تلقائياً، سيتم وضع نص بديل.\nأرسل البوستر الآن.")

# ===== استقبال البوستر والنشر النهائي =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending = [vid for vid, data in video_memory.items() if data.get("status") == "waiting"]
    if not pending: return
    v_id = pending[-1]
    
    t_msg = await message.reply_text("⏳ جاري تصميم البوستر بنبض الوقت...")
    path = await message.download()
    
    # نمرر المدة المحفوظة للدالة
    gif_path = create_pulsing_poster(path, message.caption or "حلقة جديدة", video_memory[v_id]["duration"])
    
    link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    await client.send_animation(CHANNEL_ID, animation=gif_path, 
                               caption=f"🎬 **{message.caption or 'حلقة جديدة'}**\n\n📥 [اضغط هنا للمشاهدة]({link})",
                               reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    del video_memory[v_id]
    await t_msg.delete()
    if os.path.exists(path): os.remove(path)
    if os.path.exists(gif_path): os.remove(gif_path)

app.run()
