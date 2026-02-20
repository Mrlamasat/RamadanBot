import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- الإعدادات (تأكد من وضعها في Railway/Heroku) ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# معرف القناة التي سترسل لها البوست النهائي (مثال: @MyChannel أو -100123456)
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("SmartBotV2", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# مخزن مؤقت (يفضل استبداله بـ Redis أو MongoDB مستقبلاً)
data_store = {}

@app.on_message(filters.command("start") & filters.private)
async def start_handler(c, m):
    # إذا كان الرابط يحتوي على ID فيديو (مثل: t.me/bot?start=123)
    if len(m.command) > 1:
        v_id = int(m.command[1])
        try:
            # إرسال الفيديو للمستخدم من القناة المصدر (يجب أن يكون البوت آدمن هناك)
            await c.copy_message(chat_id=m.chat.id, from_chat_id=m.chat.id, message_id=v_id)
        except Exception as e:
            await m.reply_text(f"❌ خطأ: لم أتمكن من العثور على الفيديو. {e}")
    else:
        await m.reply_text(f"أهلاً بك يا محمد، أرسل لي الفيديو هنا لضبط النشر.")

# 1. استلام الفيديو (أرسل الفيديو للبوت في الخاص مباشرة)
@app.on_message(filters.private & (filters.video | filters.document))
async def on_video(c, m):
    v_id = m.id
    msg = await m.reply_text(
        "✅ تم استلام الفيديو.\n"
        "🖼 **الآن قم بعمل (Reply) رد على هذه الرسالة وأرسل صورة البوستر مع الوصف.**",
        quote=True
    )
    data_store[msg.id] = {"v_id": v_id}

# 2. استلام البوستر والنشر النهائي
@app.on_message(filters.private & filters.photo & filters.reply)
async def on_poster(c, m):
    r_id = m.reply_to_message.id
    if r_id in data_store:
        p_id = m.photo.file_id
        caption = m.caption or "حلقة جديدة"
        v_id = data_store[r_id]["v_id"]
        
        bot = await c.get_me()
        # إنشاء رابط المشاهدة الذي سيعمل في البوت
        watch_link = f"https://t.me/{bot.username}?start={v_id}"
        
        final_caption = (
            f"🎬 {caption}\n\n"
            f"✨ الجودة: HD\n"
            f"📥 اضغط الزر لمشاهدة الحلقة"
        )
        
        # الأزرار
        btns = InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ مشاهدة الآن", url=watch_link)
        ]])
        
        try:
            # النشر في القناة العامة
            await c.send_photo(
                chat_id=PUBLIC_CHANNEL,
                photo=p_id,
                caption=final_caption,
                reply_markup=btns
            )
            await m.reply_text("🚀 تم النشر بنجاح في القناة!")
            data_store.pop(r_id) # تنظيف الذاكرة
        except Exception as e:
            await m.reply_text(f"❌ فشل النشر: {e}")
    else:
        await m.reply_text("❌ لم أتعرف على هذا الفيديو. ابدأ العملية من جديد.")

print("✅ البوت المطور يعمل الآن...")
app.run()
        link = f"https://t.me/{bot_info.username}?start={d['v_id']}"

        caption = (
            f"🎬 {d['t']}\n"
            f"🔹 الحلقة: {d.get('ep', 'غير محدد')}\n"
            f"✨ الجودة: {qual}\n\n"
            f"📥 [مشاهدة الآن]({link})"
        )

        try:
            await c.send_photo(
                chat_id=os.environ.get("PUBLIC_CHANNEL"), 
                photo=d['p'], 
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ فتح الحلقة الآن", url=link)]
                ])
            )
            await q.message.edit_text(f"🚀 تم النشر بنجاح بجودة: {qual}")
            data_store.pop(r_id, None)
        except Exception as e:
            await q.message.edit_text(f"❌ فشل النشر: {str(e)}")

# --- معالجة زر الإلغاء ---
@app.on_callback_query(filters.regex("^cancel_"))
async def on_cancel(c, q):
    r_id = int(q.data.split("_")[1])
    data_store.pop(r_id, None)
    await q.message.edit_text("❌ تم إلغاء عملية النشر وتطهير البيانات.")

# --- تشغيل البوت ---
app.run()
