import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Client("SmartBot", api_id=int(os.environ.get("API_ID", 0)), 
             api_hash=os.environ.get("API_HASH", ""), 
             bot_token=os.environ.get("BOT_TOKEN", ""))

active_session = {}

@app.on_message(filters.chat(int(os.environ.get("CHANNEL_ID", 0))) & (filters.video | filters.document))
async def vid(c, m):
    active_session.update({"v_id": str(m.id), "step": "POSTER"})
    await m.reply_text("✅ استلمت الفيديو. أرسل البوستر الآن:")

@app.on_message(filters.chat(int(os.environ.get("CHANNEL_ID", 0))) & filters.photo)
async def pos(c, m):
    if active_session.get("step") == "POSTER":
        active_session.update({"p": m.photo.file_id, "t": m.caption or "", "step": "QUAL"})
        btns = InlineKeyboardMarkup([[InlineKeyboardButton("HD", callback_data="q_HD"),
                                      InlineKeyboardButton("SD", callback_data="q_SD"),
                                      InlineKeyboardButton("4K", callback_data="q_4K")]])
        await m.reply_text("🖼 استلمت البوستر. اختر الجودة للنشر:", reply_markup=btns)

@app.on_callback_query(filters.regex("^q_"))
async def pub(c, q):
    if active_session.get("step") == "QUAL":
        qual = q.data.split("_")[1]
        user = (await c.get_me()).username
        link = f"https://t.me/{user}?start={active_session['v_id']}"
        cap = f"🎬 {active_session['t']}\n✨ الجودة: {qual}\n\n📥 [مشاهدة الآن]({link})"
        
        await c.send_photo(os.environ.get("PUBLIC_CHANNEL"), active_session['p'], cap,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=link)]]))
        await q.message.edit_text("🚀 تم النشر بنجاح!")
        active_session.clear()

app.run()
