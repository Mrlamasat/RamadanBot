import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== Logging =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===== Fetch environment variables safely =====
def get_env(name, cast=str):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} is missing in Environment Variables!")
    return cast(value)

API_ID = get_env("API_ID", int)
API_HASH = get_env("API_HASH")
BOT_TOKEN = get_env("BOT_TOKEN")
CHANNEL_ID = get_env("CHANNEL_ID", int)
PUBLIC_CHANNEL = get_env("PUBLIC_CHANNEL")  # @username أو -1001234567890

# ===== Initialize bot =====
app = Client("RamadanBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== /start command =====
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    file_id = message.command[1] if len(message.command) > 1 else None

    try:
        # تحقق من الاشتراك
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)

        # إذا مشترك ومعه رقم ملف، أرسله
        if file_id and file_id.isdigit():
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_id=int(file_id)
            )
        else:
            await message.reply_text(
                f"👋 أهلاً بك يا {message.from_user.first_name}!\n"
                "أرسل لي رابط فيديو لمشاهدته."
            )

    except UserNotParticipant:
        # لم يشترك بعد
        buttons = [
            [InlineKeyboardButton("1️⃣ اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL.strip('@')}")]
        ]
        if file_id and file_id.isdigit():
            buttons.append([InlineKeyboardButton(
                "2️⃣ تم الاشتراك.. مشاهدة الآن ✅",
                callback_data=f"check_{file_id}"
            )])

        await message.reply_text(
            f"👋 مرحباً {message.from_user.first_name}!\n\n"
            "يجب عليك الانضمام للقناة أولاً لتتمكن من مشاهدة الفيديوهات.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# ===== Handle callback "check" button =====
@app.on_callback_query(filters.regex(r"^check_"))
async def check_subscription(client, callback_query):
    file_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id

    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        await callback_query.message.delete()
        await client.copy_message(
            chat_id=user_id,
            from_chat_id=CHANNEL_ID,
            message_id=int(file_id)
        )
    except UserNotParticipant:
        await callback_query.answer(
            "⚠️ أنت لم تشترك في القناة بعد! اشترك ثم اضغط مجددًا.",
            show_alert=True
        )

# ===== When a video/document is uploaded to CHANNEL_ID =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def get_link(client, message):
    me = await client.get_me()
    share_link = f"https://t.me/{me.username}?start={message.id}"
    await message.reply_text(
        f"✅ تم الحفظ!\n\n🔗 رابط النشر:\n`{share_link}`",
        quote=True
    )

# ===== Run bot =====
if __name__ == "__main__":
    logging.info("🚀 Bot is starting...")
    app.run()
