import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8347648592:AAE1RdiNTydfOk10ufRsWm81-jv8CKecElU"
CHANNEL_ID = -1003547072209 
PUBLIC_CHANNEL = "@MoAlmohsen" 

app = Client("RamadanBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    # إذا كان الرابط يحتوي على ملف (رقم)
    file_id = message.command[1] if len(message.command) > 1 else None

    try:
        # فحص الاشتراك
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        
        # إذا كان مشتركاً ومعه رقم ملف، نرسله فوراً
        if file_id:
            await client.copy_message(chat_id=message.chat.id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
        else:
            await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}! أرسل لي رابط فيديو لمشاهدته.")

    except UserNotParticipant:
        # إذا لم يكن مشتركاً، تظهر أزرار الاشتراك والتأكيد
        buttons = [
            [InlineKeyboardButton("1️⃣ اشترك في القناة أولاً", url=f"https://t.me/MoAlmohsen")],
        ]
        # إذا كان هناك ملف، نضيف زر "تأكيد" يحمل رقم الملف
        if file_id:
            buttons.append([InlineKeyboardButton("2️⃣ تم الاشتراك.. مشاهدة الآن ✅", callback_data=f"check_{file_id}")])
        
        await message.reply_text(
            f"👋 مرحباً {message.from_user.first_name}!\n\nيجب عليك الانضمام لقناتنا الرسمية أولاً لتتمكن من مشاهدة الفيديوهات.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# معالج ضغطة زر "تأكيد الاشتراك"
@app.on_callback_query(filters.regex(r"^check_"))
async def check_subscription(client, callback_query):
    file_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        # إذا اشترك فعلاً، نحذف رسالة التنبيه ونرسل الفيديو
        await callback_query.message.delete()
        await client.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
    except UserNotParticipant:
        # إذا ضغط ولم يشترك بعد
        await callback_query.answer("⚠️ أنت لم تشترك في القناة بعد! اشترك ثم اضغط مجدداً.", show_alert=True)

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def get_link(client, message):
    me = await client.get_me()
    share_link = f"https://t.me/{me.username}?start={message.id}"
    await message.reply_text(f"✅ تم الحفظ!\n\n🔗 رابط النشر:\n`{share_link}`", quote=True)

app.run()
