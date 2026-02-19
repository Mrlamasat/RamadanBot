import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# إعدادات التسجيل (Logging)
# ==============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ==============================
# جلب متغيرات البيئة بأمان
# ==============================
def get_env(name, required=True, cast=str):
    value = os.environ.get(name)
    if required and not value:
        raise ValueError(f"Environment variable {name} is missing!")
    return cast(value) if value else None


API_ID = get_env("API_ID", cast=int)
API_HASH = get_env("API_HASH")
BOT_TOKEN = get_env("BOT_TOKEN")
CHANNEL_ID = get_env("CHANNEL_ID", cast=int)

# ==============================
# بروكسي اختياري (لو موجود)
# ==============================
PROXY_HOST = os.environ.get("PROXY_HOST")
PROXY_PORT = os.environ.get("PROXY_PORT")

proxy = None
if PROXY_HOST and PROXY_PORT:
    proxy = {
        "scheme": "socks5",
        "hostname": PROXY_HOST,
        "port": int(PROXY_PORT)
    }
    logging.info("Proxy enabled.")

# ==============================
# تشغيل البوت
# ==============================
app = Client(
    "RamadanBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    proxy=proxy,
    ipv6=False
)


# ==============================
# أمر /start
# ==============================
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
            "👋 أهلاً بك يا محمد!\n\n"
            "أرسل /start مع الرابط الخاص بالفيديو للحصول عليه."
        )


# ==============================
# توليد رابط عند رفع فيديو
# ==============================
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
            "✅ تم حفظ الملف بنجاح!\n\n"
            "اضغط الزر بالأسفل لنسخ رابط المشاركة:",
            reply_markup=keyboard,
            quote=True
        )

    except Exception as e:
        logging.error(f"Error generating link: {e}")


# ==============================
# تشغيل البوت
# ==============================
if __name__ == "__main__":
    logging.info("🚀 Bot is starting...")
    app.run()
