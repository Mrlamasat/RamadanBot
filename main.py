from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import os

# --- إعدادات النظام ---
DEFAULT_QUALITY = "HD"
qualities = ["HD", "SD", "4K"]
data_store = {} 

app = Client("my_bot", 
             api_id=int(os.environ.get("API_ID", 0)), 
             api_hash=os.environ.get("API_HASH", ""), 
             bot_token=os.environ.get("BOT_TOKEN", ""))

# --- دالة إنشاء أزرار الجودة ---
def create_quality_buttons(v_id: int, default_quality=DEFAULT_QUALITY):
    buttons = [
        [InlineKeyboardButton(
            f"✨ {q} (افتراضي)" if q == default_quality else q,
            callback_data=f"q_{q}_{v_id}"
        )] for q in qualities
    ]
    buttons.append([InlineKeyboardButton("❌ إلغاء العملية", callback_data=f"cancel_{v_id}")])
    return InlineKeyboardMarkup(buttons)

# --- معالجة اختيار الجودة والنشر ---
@app.on_callback_query(filters.regex("^q_"))
async def on_quality_selected(c, q):
    data_parts = q.data.split("_")
    # إذا كانت الجودة فارغة في الكولباك، يستخدم HD تلقائياً
    qual = data_parts[1] if len(data_parts) > 1 and data_parts[1] != "" else DEFAULT_QUALITY
    r_id = int(data_parts[2])

    if r_id in data_store:
        d = data_store[r_id]
        bot_info = await c.get_me()
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
