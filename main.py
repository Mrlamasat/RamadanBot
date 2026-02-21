import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات البوت القديم (تأكد من وضعها في إعدادات Railway للبوت القديم)
API_ID = int(os.environ.get("API_ID", 24326558)) # تأكد من وضع الآيدي الصحيح
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "توكن_البوت_القديم_هنا")

# يوزر بوتك الجديد (الذي قمنا ببرمجته تواً)
NEW_BOT_USERNAME = "Bottemo_bot" 

app = Client("OldBotRedirector", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start") & filters.private)
async def redirect_handler(client, message):
    # إذا كان المستخدم يبحث عن حلقة معينة (Deep Link)
    if len(message.command) > 1:
        v_id = message.command[1]
        # الرابط الذي سيوجه للبوت الجديد ويشغل الحلقة فوراً
        new_link = f"https://t.me/{NEW_BOT_USERNAME}?start={v_id}"
        
        text = (
            "⚠️ **تنويه هام للمشاهدين**\n\n"
            "تم نقل السيرفرات إلى بوتنا الجديد لتوفير سرعة أكبر وحماية للمحتوى.\n\n"
            "اضغط على الزر أدناه وسيبدأ الفيديو بالعمل فوراً في البوت الجديد 👇"
        )
        
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 اضغط لمشاهدة الحلقة الآن", url=new_link)]
        ])
    else:
        # إذا دخل للبوت بشكل عام بدون رابط حلقة
        text = (
            "أهلاً بك يا محمد..\n\n"
            "هذا البوت توقف عن العمل رسمياً.\n"
            "يرجى الانتقال لبوتنا الجديد لمتابعة كافة مسلسلات رمضان 2026."
        )
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 الدخول للبوت الجديد", url=f"https://t.me/{NEW_BOT_USERNAME}")]
        ])

    await message.reply_text(text, reply_markup=reply_markup)

print("✅ بوت التحويل الذكي يعمل الآن...")
app.run()
