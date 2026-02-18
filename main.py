import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from PIL import Image, ImageDraw
import shutil

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات من البيئة =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("PulsingBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== الذاكرة المؤقتة =====
video_memory = {}

# ===== دالة صنع البوستر مع زر تشغيل نابض =====
def create_pulsing_poster(base_path, title, output="final_poster.gif", pulse_frames=5):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size

        if not os.path.exists("play_button.png"):
            return base_path

        btn = Image.open("play_button.png").convert("RGBA")
        btn_w = int(width * 0.20)
        btn_h = int(btn.height * (btn_w / btn.width))
        btn = btn.resize((btn_w, btn_h), Image.LANCZOS)

        frames = []
        scale_values = [1 + 0.05*(i/pulse_frames) for i in range(pulse_frames)] + \
                       [1 - 0.05*(i/pulse_frames) for i in range(pulse_frames)]

        for scale in scale_values:
            temp = base.copy()
            w = int(btn_w * scale)
            h = int(btn_h * scale)
            btn_resized = btn.resize((w, h), Image.LANCZOS)
            temp.paste(btn_resized, ((width - w)//2, (height - h)//2), btn_resized)

            # كتابة العنوان أسفل الصورة
            draw = ImageDraw.Draw(temp)
            draw.text((10, height - 40), title, fill="white")  # يمكنك تخصيص الخط والمكان
            frames.append(temp)

        frames[0].save(output, save_all=True, append_images=frames[1:], duration=150, loop=0, disposal=2)
        return output

    except Exception as e:
        logging.error(f"Error in pulsing poster: {e}")
        return base_path

# ===== نظام الاشتراك الإجباري =====
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    file_id = message.command[1] if len(message.command) > 1 else None

    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        if file_id:
            await client.copy_message(chat_id=message.chat.id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
        else:
            await message.reply_text(f"مرحباً بك في بوت المشاهدة الحصرية! 🎬")
    except UserNotParticipant:
        buttons = [[InlineKeyboardButton("📢 اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")]]
        if file_id:
            buttons.append([InlineKeyboardButton("✅ تم الاشتراك.. مشاهدة الآن", callback_data=f"chk_{file_id}")])
        await message.reply_text(
            "⚠️ يجب الاشتراك في القناة أولاً لمشاهدة الحلقات.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_user_sub(client, callback_query):
    file_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        await callback_query.message.delete()
        await client.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
    except:
        await callback_query.answer("⚠️ يجب عليك الاشتراك في القناة أولاً!", show_alert=True)

# ===== استقبال الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    video_memory[message.id] = {"status": "waiting"}
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {message.id})\nارفع الآن صورة البوستر واكتب اسم الحلقة في Caption.")

# ===== استقبال البوستر والنشر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending = [vid for vid, data in video_memory.items() if data.get("status") == "waiting"]
    if not pending: return
    
    v_id = pending[-1]
    title = message.caption or "حلقة جديدة"
    temp_msg = await message.reply_text("⏳ جاري صنع بوستر نابض...")

    photo_path = await message.download()
    final_poster = create_pulsing_poster(photo_path, title)

    bot_username = (await client.get_me()).username
    link = f"https://t.me/{bot_username}?start={v_id}"

    # أزرار النشر
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)],
        [InlineKeyboardButton("📝 تعديل العنوان", callback_data=f"edit_{v_id}")]
    ])

    await client.send_animation(
        chat_id=CHANNEL_ID,
        animation=final_poster,
        caption=f"🎬 **{title}**\n\n📥 [اضغط هنا للمشاهدة الآن]({link})",
        reply_markup=markup
    )

    video_memory[v_id]["status"] = "posted"
    await temp_msg.edit("🔥 تم النشر بنجاح!")

    # تنظيف الملفات المؤقتة
    if os.path.exists(photo_path): os.remove(photo_path)
    if os.path.exists(final_poster): os.remove(final_poster)

# ===== تعديل العنوان بعد النشر =====
@app.on_callback_query(filters.regex(r"^edit_"))
async def start_edit(client, callback_query):
    v_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    video_memory[f"editing_{user_id}"] = {"msg_id": callback_query.message.id, "v_id": v_id}
    await callback_query.answer("📝 أرسل العنوان الجديد الآن كرسالة نصية.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text)
async def apply_new_title(client, message):
    key = f"editing_{message.from_user.id}"
    if key in video_memory:
        data = video_memory[key]
        new_title = message.text
        bot_me = await client.get_me()
        link = f"https://t.me/{bot_me.username}?start={data['v_id']}"

        try:
            await client.edit_message_caption(
                chat_id=CHANNEL_ID,
                message_id=data["msg_id"],
                caption=f"🎬 **{new_title}**\n\n📥 [اضغط هنا للمشاهدة الآن]({link})",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)],
                    [InlineKeyboardButton("📝 تعديل العنوان", callback_data=f"edit_{data['v_id']}")]
                ])
            )
            await message.reply_text("✅ تم تحديث العنوان بنجاح!")
            del video_memory[key]
        except Exception as e:
            logging.error(f"Edit Error: {e}")

if __name__ == "__main__":
    app.run()
