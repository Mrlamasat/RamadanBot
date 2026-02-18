import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# وضع البيانات مباشرة في الكود لتجنب أخطاء المنصة
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8347648592:AAE1RdiNTydfOk10ufRsWm81-jv8CKecElU"
CHANNEL_ID = -1003547072209

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
            await client.copy_message(
                chat_id=message.chat.id, 
                from_chat_id=CHANNEL_ID, 
                message_id=int(file_id)
            )
        except Exception as e:
            await message.reply(f"❌ خطأ: {e}")
    else:
        await message.reply("👋 أهلاً بك يا محمد! البوت يعمل الآن.")

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def get_link(client, message):
    try:
        me = await client.get_me()
        bot_username = me.username
        share_link = f"https://t.me/{bot_username}?start={message.id}"
        await message.reply_text(f"✅ تم الحفظ!\n\n🔗 رابط النشر:\n`{share_link}`", quote=True)
    except Exception as e:
        print(f"Error: {e}")

print("🚀 البوت بدأ العمل فعلياً...")
app.run()
