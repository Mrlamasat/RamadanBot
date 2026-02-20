import os
import logging
from pyrogram import Client, filters

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# التحقق من وجود المتغيرات
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logging.error("❌ تأكد من إعداد API_ID, API_HASH, BOT_TOKEN")
    exit(1)

app = Client("TestBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== دالة /start للتجربة =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    try:
        await message.reply_text("✅ البوت يعمل! Pyrogram متصل بالنجاح.")
        logging.info(f"/start استجابة ناجحة من المستخدم: {message.from_user.id}")
    except Exception as e:
        logging.exception(f"❌ خطأ في /start: {e}")

print("🚀 بوت الاختبار يعمل الآن...")
app.run()
