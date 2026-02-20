import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات البوت القديم
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# ضع هنا "يوزر" بوتك الجديد بدون علامة @
NEW_BOT_USERNAME = "ضع_هنا_يوزر_بوتك_الجديد" 

app = Client("OldBotRedirector", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start") & filters.private)
async def redirect_handler(client, message):
    # إذا كان المستخدم يفتح رابطاً قديماً يحتوي على ID فيديو
    if len(message.command) > 1:
        v_id = message.command[1]
        new_link = f"https://t.me/{NEW_BOT_USERNAME}?start={v_id}"
        
        text = (
            "⚠️ **تم تحديث البوت!**\n\n"
            "لقد انتقلنا إلى نسخة أسرع وأفضل. "
            "اضغط على الزر أدناه لمشاهدة الحلقة مباشرة في البوت الجديد."
        )
        
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ اضغط هنا للمشاهدة الآن", url=new_link)]
        ])
    else:
        # إذا كان المستخدم دخل للبوت بشكل عادي بدون رابط فيديو
        text = f"أهلاً بك. هذا البوت توقف، يرجى الانتقال للبوت الجديد: @{NEW_BOT_USERNAME}"
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 اذهب للبوت الجديد", url=f"https://t.me/{NEW_BOT_USERNAME}")]
        ])

    await message.reply_text(text, reply_markup=reply_markup)

app.run()
