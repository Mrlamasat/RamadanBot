import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, RPCError
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات (تأكد من ضبطها في Railway) =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("UltraFinalBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# الذاكرة المؤقتة لربط الفيديو بالبوستر
video_memory = {}

# ===== دالة صناعة البوستر الخارق (النمط الأسود الفخم) =====
def create_super_poster(base_path, title, quality="1080p"):
    try:
        base = Image.open(base_path).convert("RGBA")
        base = ImageEnhance.Contrast(base).enhance(1.4)
        width, height = base.size

        # تدرج أسود سينمائي
        overlay = Image.new("RGBA", (width, height), (0,0,0,0))
        draw_ov = ImageDraw.Draw(overlay)
        for i in range(int(height*0.4), height):
            alpha = int(255 * ((i - height*0.4) / (height*0.6)))
            draw_ov.line((0, i, width, i), fill=(0, 0, 0, min(alpha, 250)))
        base = Image.alpha_composite(base, overlay)

        draw = ImageDraw.Draw(base)
        try:
            f_bold = ImageFont.truetype("Cairo-Bold.ttf", int(width * 0.08))
            f_reg = ImageFont.truetype("Cairo-Regular.ttf", int(width * 0.04))
        except:
            f_bold = f_reg = ImageFont.load_default()

        def get_center_x(text, font):
            bbox = draw.textbbox((0, 0), text, font=font)
            return (width - (bbox[2] - bbox[0])) // 2

        # النصوص (أبيض على خلفية سوداء)
        title_y = int(height * 0.68)
        draw.text((get_center_x(title, f_bold), title_y), title, font=f_bold, fill="white")
        
        info_text = f"2026  •  حلقة جديدة  •  {quality}  •  🔥 حصري"
        draw.text((get_center_x(info_text, f_reg), title_y + int(height * 0.11)), info_text, font=f_reg, fill=(240, 240, 240, 255))

        # زر التشغيل الأسود المتوهج
        if os.path.exists("play_button.png"):
            btn = Image.open("play_button.png").convert("RGBA")
            # تحويل الزر لأسود
            btn_channels = btn.split()
            black_btn = Image.merge("RGBA", (Image.new("L", btn.size, 0), Image.new("L", btn.size, 0), Image.new("L", btn.size, 0), btn_channels[3]))
            btn_w = int(width * 0.22)
            btn_h = int(btn.height * (btn_w / btn.width))
            black_btn = black_btn.resize((btn_w, btn_h), Image.LANCZOS)

            glow_margin = 70
            glow = Image.new("RGBA", (btn_w + glow_margin, btn_h + glow_margin), (0,0,0,0))
            ImageDraw.Draw(glow).ellipse((0, 0, btn_w + glow_margin, btn_h + glow_margin), fill=(0, 0, 0, 180))
            glow = glow.filter(ImageFilter.GaussianBlur(30))
            
            base.alpha_composite(glow, ((width - btn_w - glow_margin) // 2, (height - btn_h - glow_margin) // 2))
            base.paste(black_btn, ((width - btn_w) // 2, (height - btn_h) // 2), black_btn)

        output = f"poster_{os.path.basename(base_path)}.png"
        base.convert("RGB").save(output, quality=95)
        return output
    except Exception as e:
        logging.error(f"Design Error: {e}")
        return base_path

# ===== فحص الاشتراك الإجباري عند الضغط على /start =====
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    file_id = message.command[1] if len(message.command) > 1 else None

    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        # إذا كان مشتركاً ومعه كود الحلقة
        if file_id:
            await client.copy_message(chat_id=message.chat.id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
        else:
            await message.reply_text(f"مرحباً بك يا محمد في بوت المشاهدة الحصرية! 🎬")
    except UserNotParticipant:
        # إذا لم يكن مشتركاً، تظهر أزرار الاشتراك الإجباري
        buttons = [
            [InlineKeyboardButton("1️⃣ اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")],
        ]
        if file_id:
            buttons.append([InlineKeyboardButton("2️⃣ تم الاشتراك.. اضغط للمشاهدة ✅", callback_data=f"check_{file_id}")])
        
        await message.reply_text(
            "⚠️ عذراً عزيزي، يجب عليك الاشتراك في القناة لمشاهدة المحتوى.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# ===== معالجة زر "تم الاشتراك" =====
@app.on_callback_query(filters.regex(r"^check_"))
async def check_callback(client, callback_query):
    file_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        await callback_query.message.delete()
        await client.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
    except UserNotParticipant:
        await callback_query.answer("⚠️ لم تشترك في القناة بعد!", show_alert=True)

# ===== استقبال الفيديو (المرحلة الأولى) =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    video_memory[message.id] = {"status": "waiting_poster"}
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {message.id})\nالآن أرسل صورة البوستر واكتب اسم المسلسل والحلقة في الوصف (Caption).")

# ===== استقبال البوستر والنشر النهائي (المرحلة الثانية) =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending = [vid for vid, data in video_memory.items() if data["status"] == "waiting_poster"]
    if not pending: return
    
    v_id = pending[-1]
    title = message.caption or "حلقة جديدة"
    temp_msg = await message.reply_text("⏳ جاري تصميم البوستر السينمائي الأسود...")
    
    photo_path = await message.download()
    final_poster = create_super_poster(photo_path, title)
    
    bot_username = (await client.get_me()).username
    share_link = f"https://t.me/{bot_username}?start={v_id}"
    
    caption = f"🎬 **[{title}]({share_link})**\n📺 الجودة: 1080p Ultra HD\n\n📥 [اضغط هنا للمشاهدة الآن]({share_link})"
    
    # نشر البوستر في القناة مع زر المشاهدة
    await client.send_photo(
        chat_id=CHANNEL_ID,
        photo=final_poster,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=share_link)]])
    )
    
    del video_memory[v_id]
    await temp_msg.edit("🔥 تم النشر بنجاح مع تفعيل نظام الاشتراك الإجباري!")
    
    # تنظيف الملفات
    if os.path.exists(photo_path): os.remove(photo_path)
    if os.path.exists(final_poster): os.remove(final_poster)

app.run()
