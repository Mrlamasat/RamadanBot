import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# جلب البيانات من متغيرات البيئة (Environment Variables) في Render
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

app = Client(
    "RamadanBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start"))
async def start(client, message):
    if len(message.command) > 1:
        file_id = message.command[1]
        try:
            # إرسال الملف من القناة المخزنة إلى المستخدم
            await client.copy_message(
                chat_id=message.chat.id, 
                from_chat_id=CHANNEL_ID, 
                message_id=int(file_id)
            )
        except Exception as e:
            await message.reply(f"❌ حدث خطأ في جلب الملف: {e}")
    else:
        await message.reply("👋 أهلاً بك يا محمد! أرسل الفيديو لقناتك الخاصة وسأعطيك رابط النشر.")

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def get_link(client, message):
    try:
        me = await client.get_me()
        bot_username = me.username
        # إنشاء رابط التشغيل (Deep Link)
        share_link = f"https://t.me/{bot_username}?start={message.id}"
        
        await message.reply_text(
            f"✅ تم حفظ الفيديو بنجاح!\n\n🔗 رابط النشر:\n`{share_link}`",
            quote=True
        )
    except Exception as e:
        print(f"Error: {e}")

print("🚀 البوت بدأ العمل على منصة Render...")
app.run()
