import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, RPCError
from PIL import Image

# ===== إعدادات التسجيل (Logging) =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== جلب المتغيرات من Railway =====
def get_env(name, cast=str):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"المتغير {name} غير موجود!")
    return cast(value)

API_ID = get_env("API_ID", int)
API_HASH = get_env("API_HASH")
BOT_TOKEN = get_env("BOT_TOKEN")
CHANNEL_ID = get_env("CHANNEL_ID", int)
PUBLIC_CHANNEL = get_env("PUBLIC_CHANNEL")

# ===== تهيئة البوت =====
app = Client("RamadanBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# الذاكرة المؤقتة
video_memory = {}

# ===== دالة دمج زر التشغيل في منتصف الصورة =====
def add_play_button(base_photo_path, button_path="play_button.png"):
    try:
        base_image = Image.open(base_photo_path).convert("RGBA")
        button = Image.open(button_path).convert("RGBA")

        # تصغير زر التشغيل ليكون 25% من عرض البوستر
        button_ratio = 0.25
        new_width = int(base_image.width * button_ratio)
        new_height = int(button.height * (new_width / button.width))
        
        # استخدام LANCZOS لضمان جودة الصورة في الإصدارات الجديدة
        button = button.resize((new_width, new_height), Image.LANCZOS)

        # حساب المركز
        x = (base_image.width - new_width) // 2
        y = (base_image.height - new_height) // 2
        
        # دمج الزر
        base_image.paste(button, (x, y), button)

        # حفظ النتيجة
        output_path = f"final_{os.path.basename(base_photo_path)}.png"
        base_image.save(output_path)
        return output_path
    except Exception as e:
        logging.error(f"خطأ في معالجة الصورة: {e}")
        return base_photo_path

# ===== أمر البدء /start =====
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    file_id = message.command[1] if len(message.command) > 1 else None
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        if file_id and file_id.isdigit():
            await client.copy_message(chat_id=message.chat.id, from_chat_id=CHANNEL_ID, message_id=int(file_id))
        else:
            await message.reply_text(f"👋 أهلاً بك يا {message.from_user.first_name} في بوت المشاهدة!")
    except UserNotParticipant:
        buttons = [[InlineKeyboardButton("1️⃣ اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL.strip('@')}")]]
        if file_id:
            buttons.append([InlineKeyboardButton("2️⃣ تم الاشتراك.. مشاهدة الآن ✅", callback_data=f"check_{file_id}")])
        await message.reply_text("⚠️ يجب الاشتراك أولاً لمشاهدة المحتوى.", reply_markup=InlineKeyboardMarkup(buttons))

# ===== استقبال الفيديو في المخزن =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    video_id = message.id
    video_memory[video_id] = {"photo_path": None, "caption": "حلقة جديدة", "quality": "HD", "post_id": None, "editing": False}
    
    buttons = [[InlineKeyboardButton("HD 📺", callback_data=f"q_HD_{video_id}"), 
                InlineKeyboardButton("SD 📺", callback_data=f"q_SD_{video_id}")]]
    await message.reply_text("✅ استلمت الفيديو.\n1️⃣ اختر الجودة:", reply_markup=InlineKeyboardMarkup(buttons))

# ===== ضبط الجودة =====
@app.on_callback_query(filters.regex(r"^q_"))
async def set_quality(client, callback_query):
    quality, v_id = callback_query.data.split("_")[1], int(callback_query.data.split("_")[2])
    video_memory[v_id]["quality"] = quality
    await callback_query.answer(f"✅ تم اختيار {quality}")
    await callback_query.message.edit(f"الجودة: {quality}\n2️⃣ الآن ارفع البوستر (صورة) أو اضغط تخطي:", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏩ تخطي ونشر بدون بوستر", callback_data=f"sk_{v_id}")]]))

# ===== استقبال البوستر ومعالجته =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    pending = [vid for vid, data in video_memory.items() if data["photo_path"] is None]
    if not pending: return
    
    v_id = pending[-1]
    msg = await message.reply_text("⏳ جاري دمج زر التشغيل وحفظ الحقوق...")
    
    # تحميل الصورة الأصلية
    photo_file = await message.download()
    
    # معالجة الصورة وإضافة زر التشغيل
    final_photo = add_play_button(photo_file)
    
    video_memory[v_id]["photo_path"] = final_photo
    video_memory[v_id]["caption"] = message.caption or "مشاهدة ممتعة للحلقة"

    await post_now(client, v_id)
    await msg.edit("✅ تم النشر باحترافية!")

# ===== عملية النشر النهائية =====
async def post_now(client, v_id):
    data = video_memory[v_id]
    me = await client.get_me()
    share_link = f"https://t.me/{me.username}?start={v_id}"
    
    # تنسيق Caption مع رابط مخفي على العنوان
    caption = (
        f"🎬 **[{data['caption']}]({share_link})**\n"
        f"📺 **الجودة:** {data['quality']}\n"
        f"🛡️ حقوق النشر محفوظة لـ {PUBLIC_CHANNEL}\n\n"
        f"📥 [اضغط هنا للمشاهدة الآن]({share_link})"
    )
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎞 مشاهدة الآن", url=share_link)],
        [InlineKeyboardButton("✏️ تعديل العنوان", callback_data=f"edit_{v_id}")]
    ])

    if data["photo_path"]:
        post = await client.send_photo(chat_id=CHANNEL_ID, photo=data["photo_path"], caption=caption, reply_markup=markup)
        if os.path.exists(data["photo_path"]): os.remove(data["photo_path"]) # تنظيف الملفات المؤقتة
    else:
        post = await client.send_message(chat_id=CHANNEL_ID, text=caption, reply_markup=markup)
    
    video_memory[v_id]["post_id"] = post.id

# ===== ميزة التعديل =====
@app.on_callback_query(filters.regex(r"^edit_"))
async def start_edit(client, callback_query):
    v_id = int(callback_query.data.split("_")[1])
    video_memory[v_id]["editing"] = True
    await callback_query.answer("📝 أرسل العنوان الجديد الآن كرسالة نصية.", show_alert=True)

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command("start"))
async def apply_edit(client, message):
    editing_vid = next((v for v, d in video_memory.items() if d.get("editing")), None)
    if not editing_vid: return

    new_title = message.text[:1000]
    data = video_memory[editing_vid]
    share_link = f"https://t.me/{(await client.get_me()).username}?start={editing_vid}"
    
    try:
        await client.edit_message_caption(
            chat_id=CHANNEL_ID,
            message_id=data["post_id"],
            caption=f"🎬 **[{new_title}]({share_link})**\n📺 الجودة: {data['quality']}\n\n📢 {PUBLIC_CHANNEL}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎞 مشاهدة الآن", url=share_link)]])
        )
        video_memory[editing_vid]["editing"] = False
        await message.reply_text("✅ تم تحديث العنوان!")
    except Exception as e:
        logging.error(f"خطأ في التعديل: {e}")

if __name__ == "__main__":
    app.run()
