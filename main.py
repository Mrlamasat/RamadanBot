import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, RPCError

# ===== إعدادات التسجيل (Logging) =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===== جلب المتغيرات من Railway بأمان =====
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

# ذاكرة مؤقتة لحفظ البوسترات لكل فيديو
video_posters = {}  # المفتاح: message_id للفيديو، القيمة: file_id للصورة

# ===== أمر البدء /start مع فحص الاشتراك الإجباري =====
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    file_id = message.command[1] if len(message.command) > 1 else None

    try:
        # فحص هل المستخدم عضو في القناة العامة
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
        buttons = [
            [InlineKeyboardButton("1️⃣ اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL.strip('@')}")]
        ]
        if file_id:
            buttons.append([InlineKeyboardButton("2️⃣ تم الاشتراك.. مشاهدة الآن ✅", callback_data=f"check_{file_id}")])

        await message.reply_text(
            f"⚠️ عذراً يا {message.from_user.first_name}!\n\nيجب عليك الاشتراك في قناتنا الرسمية أولاً لتتمكن من مشاهدة المحتوى.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except RPCError as e:
        logging.error(f"خطأ عند فحص الاشتراك: {e}")
        await message.reply_text("⚠️ حدث خطأ مؤقت، حاول لاحقاً.")

# ===== معالج زر "تأكيد الاشتراك" =====
@app.on_callback_query(filters.regex(r"^check_"))
async def check_subscription(client, callback_query):
    file_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id

    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        await callback_query.message.delete()
        await client.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
    except UserNotParticipant:
        await callback_query.answer("⚠️ أنت لم تشترك في القناة بعد! اشترك ثم اضغط مجدداً.", show_alert=True)
    except RPCError as e:
        logging.error(f"خطأ عند التحقق من الاشتراك: {e}")
        await callback_query.answer("⚠️ حدث خطأ مؤقت، حاول لاحقاً.", show_alert=True)

# ===== استقبال الفيديو / المستند في قناة المخزن =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def get_link(client, message):
    video_posters[message.id] = None  # مؤقتاً بدون بوستر
    await message.reply_text(
        "📸 يمكنك الآن رفع صورة البوستر لهذا الفيديو (اختياري)."
        "\nإذا لم ترغب في إضافة بوستر، سيتم نشر الفيديو مباشرة.",
        quote=True
    )

# ===== استقبال الصورة وربطها بالفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def save_photo(client, message):
    # إيجاد أحدث فيديو بدون بوستر
    pending_videos = [vid_id for vid_id, pid in video_posters.items() if pid is None]
    if not pending_videos:
        await message.reply_text("⚠️ لا يوجد فيديو منتظر بوستر.", quote=True)
        return

    latest_video_id = pending_videos[-1]
    video_posters[latest_video_id] = message.photo.file_id
    await message.reply_text(f"✅ تم حفظ البوستر للفيديو {latest_video_id}", quote=True)

    # إرسال المنشور النهائي (فيديو + بوستر)
    share_link = f"https://t.me/{(await client.get_me()).username}?start={latest_video_id}"

    await client.send_photo(
        chat_id=CHANNEL_ID,
        photo=message.photo.file_id,
        caption=(
            "🎬 **حلقة جديدة جاهزة للمشاهدة!**\n\n"
            "📺 **المحتوى:** جودة عالية HD\n"
            "📥 **المشاهدة:** اضغط على الزر بالأسفل للانتقال للحلقة.\n\n"
            f"📢 **القناة الرسمية:** {PUBLIC_CHANNEL}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎞 مشاهدة الحلقة الآن", url=share_link)],
            [InlineKeyboardButton("📢 تابعنا للمزيد", url=f"https://t.me/{PUBLIC_CHANNEL.strip('@')}")]
        ])
    )

    # إزالة من الذاكرة لتجهيز الفيديو التالي
    video_posters.pop(latest_video_id)

# ===== تشغيل البوت =====
if __name__ == "__main__":
    logging.info("🚀 البوت بدأ العمل بنجاح...")
    app.run()
