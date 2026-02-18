import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, RPCError

# ===== إعدادات التسجيل =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===== جلب المتغيرات =====
def get_env(name, cast=str):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"المتغير {name} غير موجود في إعدادات Railway!")
    return cast(value)

API_ID = get_env("API_ID", int)
API_HASH = get_env("API_HASH")
BOT_TOKEN = get_env("BOT_TOKEN")
CHANNEL_ID = get_env("CHANNEL_ID", int)
PUBLIC_CHANNEL = get_env("PUBLIC_CHANNEL")  # مثال: @MoAlmohsen

# ===== تهيئة البوت =====
app = Client("RamadanBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ذاكرة مؤقتة لكل فيديو: message_id -> dict (photo_id, caption, quality)
video_memory = {}

# ===== أمر البدء /start مع فحص الاشتراك =====
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    file_id = message.command[1] if len(message.command) > 1 else None

    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)

        if file_id and file_id.isdigit():
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_id=int(file_id)
            )
        else:
            await message.reply_text(f"👋 أهلاً بك يا {message.from_user.first_name} في بوت المشاهدة!")

    except UserNotParticipant:
        buttons = [[InlineKeyboardButton("1️⃣ اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL.strip('@')}")]]
        if file_id:
            buttons.append([InlineKeyboardButton("2️⃣ تم الاشتراك.. مشاهدة الآن ✅", callback_data=f"check_{file_id}")])
        await message.reply_text(
            f"⚠️ عذراً يا {message.from_user.first_name}!\nيجب عليك الاشتراك أولاً.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except RPCError as e:
        logging.error(f"خطأ عند فحص الاشتراك: {e}")
        await message.reply_text("⚠️ حدث خطأ مؤقت، حاول لاحقاً.")

# ===== زر "تأكيد الاشتراك" =====
@app.on_callback_query(filters.regex(r"^check_"))
async def check_subscription(client, callback_query):
    file_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        await callback_query.message.delete()
        await client.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
    except UserNotParticipant:
        await callback_query.answer("⚠️ لم تشترك بعد! اشترك ثم اضغط مجدداً.", show_alert=True)
    except RPCError as e:
        logging.error(f"خطأ عند التحقق من الاشتراك: {e}")
        await callback_query.answer("⚠️ حدث خطأ مؤقت.", show_alert=True)

# ===== استقبال الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    video_memory[message.id] = {"photo_id": None, "caption": None, "quality": None}

    # أزرار اختيار الجودة
    quality_buttons = [
        [InlineKeyboardButton("HD 📺", callback_data=f"quality_HD_{message.id}"),
         InlineKeyboardButton("SD 📺", callback_data=f"quality_SD_{message.id}")]
    ]
    await message.reply_text(
        "✅ تم استقبال الفيديو!\nاختر الجودة المطلوبة قبل رفع البوستر أو النشر.",
        reply_markup=InlineKeyboardMarkup(quality_buttons)
    )

# ===== اختيار الجودة =====
@app.on_callback_query(filters.regex(r"^quality_(HD|SD)_"))
async def set_quality(client, callback_query):
    quality, video_id = callback_query.data.split("_")[1], int(callback_query.data.split("_")[2])
    if video_id not in video_memory:
        await callback_query.answer("⚠️ هذا الفيديو لم يعد موجوداً.", show_alert=True)
        return

    video_memory[video_id]["quality"] = quality
    await callback_query.answer(f"✅ تم اختيار جودة {quality} للفيديو.", show_alert=True)

    # بعد اختيار الجودة، نعرض أزرار رفع بوستر أو تخطي
    buttons = [
        [InlineKeyboardButton("📸 رفع بوستر للفيديو", callback_data=f"upload_{video_id}")],
        [InlineKeyboardButton("⏩ تخطي البوستر ونشر الفيديو", callback_data=f"skip_{video_id}")]
    ]
    await callback_query.message.edit(
        f"تم اختيار جودة {quality} للفيديو. الآن اختر: رفع بوستر أو تخطي والنشر مباشرة.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ===== زر رفع البوستر =====
@app.on_callback_query(filters.regex(r"^upload_"))
async def upload_poster_callback(client, callback_query):
    video_id = int(callback_query.data.split("_")[1])
    await callback_query.answer("📸 الآن أرسل صورة البوستر مع Caption اختياري.", show_alert=True)

# ===== زر تخطي البوستر =====
@app.on_callback_query(filters.regex(r"^skip_"))
async def skip_poster_callback(client, callback_query):
    video_id = int(callback_query.data.split("_")[1])
    if video_id not in video_memory:
        await callback_query.answer("⚠️ هذا الفيديو لم يعد موجوداً.", show_alert=True)
        return

    share_link = f"https://t.me/{(await client.get_me()).username}?start={video_id}"
    quality = video_memory[video_id]["quality"] or "HD"
    caption = (
        "🎬 **حلقة جديدة جاهزة للمشاهدة!**\n"
        f"📺 **الجودة:** {quality}\n"
        "📥 **المشاهدة:** اضغط على الزر بالأسفل للانتقال للحلقة.\n\n"
        f"📢 **القناة الرسمية:** {PUBLIC_CHANNEL}"
    )

    await client.copy_message(chat_id=CHANNEL_ID, from_chat_id=CHANNEL_ID, message_id=video_id)
    await client.send_message(
        chat_id=CHANNEL_ID,
        text=caption,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎞 مشاهدة الحلقة الآن", url=share_link)],
            [InlineKeyboardButton("📢 تابعنا للمزيد", url=f"https://t.me/{PUBLIC_CHANNEL.strip('@')}")]
        ])
    )
    video_memory.pop(video_id)

# ===== استقبال الصورة وربطها بالفيديو مع Caption =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending_videos = [vid_id for vid_id, data in video_memory.items() if data["photo_id"] is None]
    if not pending_videos:
        await message.reply_text("⚠️ لا يوجد فيديو منتظر بوستر. ارفع الفيديو أولاً.", quote=True)
        return

    latest_video_id = pending_videos[-1]
    video_memory[latest_video_id]["photo_id"] = message.photo.file_id
    video_memory[latest_video_id]["caption"] = message.caption or "حلقة جديدة جاهزة للمشاهدة!"

    share_link = f"https://t.me/{(await client.get_me()).username}?start={latest_video_id}"
    quality = video_memory[latest_video_id]["quality"] or "HD"
    custom_caption = video_memory[latest_video_id]["caption"][:1020]

    await message.reply_text(f"✅ تم ربط البوستر بالفيديو {latest_video_id}", quote=True)

    # إرسال المنشور النهائي
    await client.send_photo(
        chat_id=CHANNEL_ID,
        photo=message.photo.file_id,
        caption=(
            f"🎬 **{custom_caption}**\n"
            f"📺 **الجودة:** {quality}\n"
            "📥 **المشاهدة:** اضغط على الزر بالأسفل للانتقال للحلقة.\n\n"
            f"📢 **القناة الرسمية:** {PUBLIC_CHANNEL}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎞 مشاهدة الحلقة الآن", url=share_link)],
            [InlineKeyboardButton("📢 تابعنا للمزيد", url=f"https://t.me/{PUBLIC_CHANNEL.strip('@')}")]
        ])
    )
    video_memory.pop(latest_video_id)

# ===== تشغيل البوت =====
if __name__ == "__main__":
    logging.info("🚀 البوت بدأ العمل بنجاح...")
    app.run()
