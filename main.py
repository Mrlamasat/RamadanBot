import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from PIL import Image, ImageDraw, ImageFont

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات (Railway Environment Variables) =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# الذاكرة المؤقتة للربط والتعديل
video_memory = {}

# ===== دالة صناعة البوستر (تصميم حاد مع زر أحمر) =====
def create_clean_poster(base_path, title):
    try:
        base = Image.open(base_path).convert("RGBA")
        width, height = base.size
        
        # إضافة زر التشغيل الأحمر (بدون أي توهج)
        if os.path.exists("play_button.png"):
            btn = Image.open("play_button.png").convert("RGBA")
            btn_channels = btn.split()
            # تلوين الزر بالأحمر الصريح (229, 9, 20)
            red_color = (229, 9, 20) 
            red_btn = Image.merge("RGBA", (
                Image.new("L", btn.size, red_color[0]), 
                Image.new("L", btn.size, red_color[1]), 
                Image.new("L", btn.size, red_color[2]), 
                btn_channels[3] # الحفاظ على الشفافية
            ))
            
            btn_w = int(width * 0.20)
            btn_h = int(btn.height * (btn_w / btn.width))
            red_btn = red_btn.resize((btn_w, btn_h), Image.LANCZOS)
            
            # وضع الزر في المركز مباشرة بدون تأثيرات
            base.paste(red_btn, ((width - btn_w) // 2, (height - btn_h) // 2), red_btn)

        output = f"final_{os.path.basename(base_path)}.png"
        base.convert("RGB").save(output, quality=100)
        return output
    except Exception as e:
        logging.error(f"Error in Image Processing: {e}")
        return base_path

# ===== نظام الاشتراك الإجباري والتشغيل =====
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    file_id = message.command[1] if len(message.command) > 1 else None

    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        if file_id:
            # إذا كان مشتركاً، يحصل على الحلقة فوراً
            await client.copy_message(chat_id=message.chat.id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
        else:
            await message.reply_text(f"مرحباً بك يا محمد في بوت المشاهدة الحصرية! 🎬")
    except UserNotParticipant:
        # إذا لم يكن مشتركاً، تظهر أزرار الاشتراك
        buttons = [[InlineKeyboardButton("📢 اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")]]
        if file_id:
            buttons.append([InlineKeyboardButton("✅ تم الاشتراك.. مشاهدة الآن", callback_data=f"chk_{file_id}")])
        
        await message.reply_text(
            "⚠️ عذراً، يجب عليك الاشتراك في القناة أولاً لتتمكن من مشاهدة الحلقات.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# ===== التحقق من الاشتراك عبر الأزرار =====
@app.on_callback_query(filters.regex(r"^chk_"))
async def check_user_sub(client, callback_query):
    file_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        await callback_query.message.delete()
        await client.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
    except:
        await callback_query.answer("⚠️ يجب عليك الاشتراك في القناة أولاً!", show_alert=True)

# ===== استقبال الفيديو في القناة الرئيسية =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    video_memory[message.id] = {"status": "waiting"}
    await message.reply_text(f"✅ تم حفظ الفيديو (ID: {message.id})\nالآن أرسل البوستر واكتب العنوان في الـ Caption.")

# ===== استقبال البوستر والنشر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending = [vid for vid, data in video_memory.items() if data.get("status") == "waiting"]
    if not pending: return
    
    v_id = pending[-1]
    title = message.caption or "حلقة جديدة"
    
    msg = await message.reply_text("⏳ جاري معالجة البوستر...")
    
    path = await message.download()
    final_img = create_clean_poster(path, title)
    
    bot_me = await client.get_me()
    link = f"https://t.me/{bot_me.username}?start={v_id}"
    
    # أزرار المنشور: مشاهدة + تعديل
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)],
        [InlineKeyboardButton("📝 تعديل العنوان", callback_data=f"edit_{v_id}")]
    ])
    
    await client.send_photo(
        chat_id=CHANNEL_ID,
        photo=final_img,
        caption=f"🎬 **{title}**\n\n📥 [مشاهدة الآن]({link})",
        reply_markup=markup
    )
    
    video_memory[v_id] = {"status": "posted"} # تحديث الحالة
    await msg.edit("🔥 تم النشر بنجاح!")
    
    if os.path.exists(path): os.remove(path)
    if os.path.exists(final_img): os.remove(final_img)

# ===== ميزة تعديل العنوان =====
@app.on_callback_query(filters.regex(r"^edit_"))
async def start_edit(client, callback_query):
    v_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    video_memory[f"editing_{user_id}"] = {"msg_id": callback_query.message.id, "v_id": v_id}
    await callback_query.answer("📝 أرسل العنوان الجديد الآن كرسالة نصية.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text)
async def apply_new_title(client, message):
    key = f"editing_{message.from_user.id}"
    if key in video_memory:
        data = video_memory[key]
        new_title = message.text
        bot_me = await client.get_me()
        link = f"https://t.me/{bot_me.username}?start={data['v_id']}"
        
        try:
            await client.edit_message_caption(
                chat_id=CHANNEL_ID,
                message_id=data["msg_id"],
                caption=f"🎬 **{new_title}**\n\n📥 [مشاهدة الآن]({link})",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ مشاهدة الحلقة الآن", url=link)],
                    [InlineKeyboardButton("📝 تعديل العنوان", callback_data=f"edit_{data['v_id']}")]
                ])
            )
            await message.reply_text("✅ تم تحديث العنوان بنجاح!")
            del video_memory[key]
        except Exception as e:
            logging.error(f"Edit Error: {e}")

if __name__ == "__main__":
    app.run()
