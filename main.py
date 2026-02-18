import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("UltraStudioBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
video_memory = {}

# ===== دالة صناعة البوستر الخارق (الدمج السينمائي) =====
def create_super_poster(base_path, title, quality="1080p"):
    try:
        base = Image.open(base_path).convert("RGBA")
        # تحسين الألوان والتباين لجعلها سينمائية أكثر
        base = ImageEnhance.Contrast(base).enhance(1.3)
        base = ImageEnhance.Color(base).enhance(1.2)
        width, height = base.size

        # 1. إضافة تدرج أسود سفلي (Cinematic Gradient)
        overlay = Image.new("RGBA", (width, height), (0,0,0,0))
        draw_ov = ImageDraw.Draw(overlay)
        for i in range(int(height*0.5), height):
            alpha = int(255 * ((i - height*0.5) / (height*0.5)))
            draw_ov.line((0, i, width, i), fill=(0, 0, 0, min(alpha, 240)))
        base = Image.alpha_composite(base, overlay)

        draw = ImageDraw.Draw(base)
        
        # تحميل الخطوط
        try:
            f_bold = ImageFont.truetype("Cairo-Bold.ttf", int(width * 0.08))
            f_reg = ImageFont.truetype("Cairo-Regular.ttf", int(width * 0.04))
        except:
            f_bold = f_reg = ImageFont.load_default()

        # 2. رسم العنوان (Title)
        def get_center_x(text, font):
            bbox = draw.textbbox((0, 0), text, font=font)
            return (width - (bbox[2] - bbox[0])) // 2

        title_y = int(height * 0.65)
        draw.text((get_center_x(title, f_bold), title_y), title, font=f_bold, fill="white")

        # 3. شريط المعلومات (Info Bar) مثل Netflix
        info_text = f"2026  •  حلقة جديدة  •  {quality}  •  🔥 حصري"
        info_y = title_y + int(height * 0.12)
        draw.text((get_center_x(info_text, f_reg), info_y), info_text, font=f_reg, fill="#E50914") # لون أحمر نتفليكس

        # 4. إضافة زر التشغيل المتوهج في المنتصف
        btn = Image.open("play_button.png").convert("RGBA")
        btn_w = int(width * 0.22)
        btn_h = int(btn.height * (btn_w / btn.width))
        btn = btn.resize((btn_w, btn_h), Image.LANCZOS)

        # تأثير التوهج (Glow)
        glow = Image.new("RGBA", (btn_w+60, btn_h+60), (0,0,0,0))
        ImageDraw.Draw(glow).ellipse((0,0,btn_w+60,btn_h+60), fill=(229, 9, 20, 150))
        glow = glow.filter(ImageFilter.GaussianBlur(25))
        
        base.alpha_composite(glow, ((width-btn_w-60)//2, (height-btn_h-60)//2))
        base.paste(btn, ((width-btn_w)//2, (height-btn_h)//2), btn)

        # 5. إطار أحمر نحيف جداً (اختياري للفخامة)
        draw.rectangle([0, 0, width-1, height-1], outline="#E50914", width=3)

        output = f"final_{os.path.basename(base_path)}.png"
        base.convert("RGB").save(output, quality=95)
        return output
    except Exception as e:
        logging.error(f"Error in design: {e}")
        return base_path

# ===== استقبال الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    video_memory[message.id] = {"quality": "1080p Ultra HD"}
    await message.reply_text("✅ استلمت الفيديو.\nارفع الآن صورة البوستر واكتب اسم الحلقة في الـ Caption.")

# ===== استقبال البوستر والنشر الفوري =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending = list(video_memory.keys())
    if not pending: return
    
    v_id = pending[-1]
    title = message.caption or "حلقة جديدة"
    msg = await message.reply_text("🎬 جاري معالجة البوستر الخارق...")
    
    photo = await message.download()
    final_img = create_super_poster(photo, title, video_memory[v_id]["quality"])
    
    share_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    
    caption = f"🎬 **[{title}]({share_link})**\n📺 الجودة: {video_memory[v_id]['quality']}\n\n📢 {PUBLIC_CHANNEL}"
    
    await client.send_photo(
        chat_id=CHANNEL_ID,
        photo=final_img,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=share_link)]])
    )
    
    video_memory.pop(v_id)
    await msg.edit("🔥 تم النشر بنجاح بمستوى Netflix Ultra!")
    if os.path.exists(photo): os.remove(photo)
    if os.path.exists(final_img): os.remove(final_img)

app.run()
