import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# بياناتك الأساسية
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8347648592:AAE1RdiNTydfOk10ufRsWm81-jv8CKecElU"
CHANNEL_ID = -1003547072209  # قناة المخزن
PUBLIC_CHANNEL = "@MoAlmohsen"  # قناتك العامة الجديدة

app = Client("RamadanBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(client, message):
    # التحقق من الاشتراك الإجباري في قناتك
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
    except UserNotParticipant:
        # رسالة تظهر للمستخدم غير المشترك
        return await message.reply_text(
            f"👋 أهلاً بك يا {message.from_user.first_name}!\n\n⚠️ لمشاهدة المحتوى، يرجى الاشتراك في القناة الرسمية أولاً ثم عد للضغط على الرابط مجدداً.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ اضغط هنا للاشتراك في القناة", url=f"https://t.me/MoAlmohsen")]
            ])
        )

    # إذا كان مشتركاً، يتم إرسال الفيديو المطلوب
    if len(message.command) > 1:
        file_id = message.command[1]
        try:
            await client.copy_message(
                chat_id=message.chat.id, 
                from_chat_id=CHANNEL_ID, 
                message_id=int(file_id)
            )
        except Exception as e:
            await message.reply(f"❌ خطأ: لم أستطع العثور على هذا الفيديو. تأكد من وجوده في المخزن.")
    else:
        await message.reply(f"أهلاً بك يا {message.from_user.first_name}! أرسل لي رابطاً صالحاً لمشاهدة الفيديو.")

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def get_link(client, message):
    try:
        me = await client.get_me()
        share_link = f"https://t.me/{me.username}?start={message.id}"
        await message.reply_text(f"✅ تم حفظ الفيديو بنجاح!\n\n🔗 رابط النشر المخصص:\n`{share_link}`", quote=True)
    except Exception as e:
        print(f"Error: {e}")

app.run()
