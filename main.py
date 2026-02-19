import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== Logging =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===== Helper function to get environment variables safely =====
def get_env(name, cast=str):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} is missing in Environment Variables!")
    return cast(value)

# ===== Fetch environment variables =====
API_ID = get_env("API_ID", int)
API_HASH = get_env("API_HASH")
BOT_TOKEN = get_env("BOT_TOKEN")
CHANNEL_ID = get_env("CHANNEL_ID", int)

# ===== Start bot =====
app = Client(
    "RamadanBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    ipv6=False
)

# ===== /start command =====
@app.on_message(filters.command("start"))
async def start(client, message):
    if len(message.command) > 1:
        file_id = message.command[1]

        if not file_id.isdigit():
            await message.reply("❌ رابط غير صالح.")
            return

        try:
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_id=int(file_id)
            )
        except Exception as e:
            logging.error(f"Copy failed: {e}")
            await message.reply("❌ لا يمكن جلب هذا الملف.")
    else:
        await message.reply(
            "👋 أهلاً بك!\n\n"
            "أرسل /start مع رابط الفيديو للحصول عليه."
        )

# ===== Generate share link when a video/document is uploaded =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def generate_link(client, message):
    try:
        me = await client.get_me()
        bot_username = me.username

        share_link = f"https://t.me/{bot_username}?start={message.id}"

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔗 مشاركة الرابط", url=share_link)]]
        )

        await message.reply_text(
            "✅ تم حفظ الملف بنجاح!\n\nاضغط الزر بالأسفل لنسخ رابط المشاركة:",
            reply_markup=keyboard,
            quote=True
        )

    except Exception as e:
        logging.error(f"Error generating link: {e}")

# ===== Run bot =====
if __name__ == "__main__":
    logging.info("🚀 Bot is starting...")
    app.run()
