import os
import asyncio
from pyrogram import Client, filters

# استلام المتغيرات
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("TestBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("✅ الكود الجديد شغال والاتصال سليم!")

print("🚀 جاري تشغيل البوت للتجربة...")
app.run()
