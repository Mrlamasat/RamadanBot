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

app = Client("MohammedFixBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

video_memory = {}

def format_duration(seconds):
    if not seconds: return "مشاهدة ممتعة"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d} دقيقة"

# ===== دالة صنع البوستر الاحترافي =====
def create_super_poster(base_path, duration_text, output="final_animation.gif"):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size
        try:
            font_info = ImageFont.truetype("Cairo-Bold.ttf", int(width * 0.04))
        except:
            font_info = ImageFont.load_default()

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
        scales = [1.0, 1.03, 1.06, 1.03, 1.0, 0.97]

        for scale in scales:
            temp = base.copy()
            draw = ImageDraw.Draw(temp)
            bar_h = int(height * 0.12)
            draw.rectangle([0, height - bar_h, width, height], fill=(0, 0, 0, 230))
            
            info_text = f"2026  •  {duration_text}  •  1080p  •  🔥 حصري"
            bbox = draw.textbbox((0, 0), info_text, font=font_info)
            tx = (width - (bbox[2] - bbox[0])) // 2
            draw.text((tx, height - bar_h + (bar_h // 3)), info_text, font=font_info, fill="white")

            w_p, h_p = int(btn_w * scale), int(btn_h * scale)
            btn_resized = red_btn.resize((w_p, h_p), Image.LANCZOS)
            temp.paste(btn_resized, ((width - w_p)//2, (height - h_p)//2), btn_resized)
            frames.append(temp.convert("RGB"))

        frames[0].save(output, save_all=True, append_images=frames[1:], duration=120, loop=0)
        return output
    except Exception as e:
        logging.error(f"Design error: {e}")
        return base_path

# ===== نظام معالجة رسالة Start (الحل الجذري) =====
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    # التأكد من استخراج كود الفيديو من الرابط (start=ID)
    file_id = message.command[1] if len(message.command) > 1 else None

    try:
        # فحص الاشتراك الإجباري
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        
        if file_id:
            # إذا كان مشتركاً ومعه كود الفيديو، نرسل الفيديو فوراً
            await client.copy_message(chat_id=message.chat.id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
        else:
            await message.reply_text(f"أهلاً بك يا محمد! البوت يعمل بنجاح، اضغط على روابط الحلقات من القناة للمشاهدة.")
            
    except UserNotParticipant:
        # إذا لم يكن مشتركاً، تظهر أزرار الاشتراك مع الحفاظ على كود الفيديو
        buttons = [[InlineKeyboardButton("📢 اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")]]
        if file_id:
            buttons.append([InlineKeyboardButton("✅ تم الاشتراك.. مشاهدة الآن", callback_data=f"chk_{file_id}")])
        
        await message.reply_text(
            "⚠️ عذراً، يجب عليك الاشتراك في القناة أولاً لمشاهدة المحتوى الحصري.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# ===== التحقق من الاشتراك (زر Callback) =====
@app.on_callback_query(filters.regex(r"^chk_"))
async def check_user_sub(client, callback_query):
    file_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        await callback_query.message.delete()
        await client.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
    except UserNotParticipant:
        await callback_query.answer("⚠️ لم تشترك في القناة بعد!", show_alert=True)

# ===== استقبال الفيديو وحفظ المدة =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = 0
    if message.video: duration = message.video.duration
    elif message.document: duration = getattr(message.document, "duration", 0)

    d_text = format_duration(duration)
    video_memory[message.id] = {"duration": d_text, "status": "waiting"}
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\nالآن أرسل البوستر واكتب العنوان.")

# ===== استقبال البوستر والنشر النهائي =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending = [vid for vid, data in video_memory.items() if data.get("status") == "waiting"]
    if not pending: return
    v_id = pending[-1]
    
    t_msg = await message.reply_text("⏳ جاري إنشاء المنشور بنظام الربط...")
    path = await message.download()
    gif_path = create_super_poster(path, video_memory[v_id]["duration"])
    
    bot_me = await client.get_me()
    # تأكدنا هنا أن الرابط يحتوي على ID الفيديو
    link = f"https://t.me/{bot_me.username}?start={v_id}"
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)],
        [InlineKeyboardButton("📝 تعديل العنوان", callback_data=f"edit_{v_id}")]
    ])
    
    await client.send_animation(
        CHANNEL_ID, animation=gif_path,
        caption=f"🎬 **{message.caption or 'حلقة جديدة'}**\n\n📥 [اضغط هنا للمشاهدة الآن]({link})",
        reply_markup=markup
    )
    
    video_memory[v_id]["status"] = "posted"
    await t_msg.delete()
    if os.path.exists(path): os.remove(path)
    if os.path.exists(gif_path): os.remove(gif_path)

# ===== تعديل العنوان =====
@app.on_callback_query(filters.regex(r"^edit_"))
async def start_edit(client, query):
    video_memory[f"editing_{query.from_user.id}"] = {"mid": query.message.id, "vid": query.data.split("_")[1]}
    await query.answer("📝 أرسل العنوان الجديد.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text)
async def apply_edit(client, message):
    key = f"editing_{message.from_user.id}"
    if key in video_memory:
        d = video_memory[key]
        link = f"https://t.me/{(await client.get_me()).username}?start={d['vid']}"
        await client.edit_message_caption(CHANNEL_ID, d['mid'], caption=f"🎬 **{message.text}**\n\n📥 [مشاهدة الآن]({link})",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)], [InlineKeyboardButton("📝 تعديل العنوان", callback_data=f"edit_{d['vid']}")]]))
        await message.reply_text("✅ تم التعديل!")
        del video_memory[key]

app.run()
