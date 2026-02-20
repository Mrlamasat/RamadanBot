import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Client("SmartBot", api_id=int(os.environ.get("API_ID", 0)), 
             api_hash=os.environ.get("API_HASH", ""), 
             bot_token=os.environ.get("BOT_TOKEN", ""))

# قاموس لحفظ البيانات بناءً على ID رسالة البوت
data_store = {}

# 1. عند إرسال الفيديو
@app.on_message(filters.chat(int(os.environ.get("CHANNEL_ID", 0))) & (filters.video | filters.document))
async def on_video(c, m):
    msg = await m.reply_text("✅ استلمت الفيديو.\n👈 **قم بالرد على هذه الرسالة بصورة البوستر:**", quote=True)
    # نربط العملية بـ ID رسالة البوت هذه
    data_store[msg.id] = {"v_id": m.id}

# 2. عند الرد بالبوستر
@app.on_message(filters.chat(int(os.environ.get("CHANNEL_ID", 0))) & filters.photo & filters.reply)
async def on_poster(c, m):
    reply_id = m.reply_to_message.id
    if reply_id in data_store:
        data_store[reply_id].update({"p": m.photo.file_id, "t": m.caption or "حلقة جديدة"})
        msg = await m.reply_text("🖼 تم حفظ البوستر.\n👈 **قم بالرد على هذه الرسالة برقم الحلقة:**", quote=True)
        # ننقل البيانات لـ ID الرسالة الجديدة
        data_store[msg.id] = data_store.pop(reply_id)

# 3. عند الرد برقم الحلقة
@app.on_message(filters.chat(int(os.environ.get("CHANNEL_ID", 0))) & filters.text & filters.reply)
async def on_ep(c, m):
    reply_id = m.reply_to_message.id
    if reply_id in data_store:
        data_store[reply_id].update({"ep": m.text})
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("HD", callback_data=f"q_HD_{reply_id}"),
             InlineKeyboardButton("SD", callback_data=f"q_SD_{reply_id}"),
             InlineKeyboardButton("4K", callback_data=f"q_4K_{reply_id}")]
        ])
        await m.reply_text(f"🔢 الحلقة {m.text} جاهزة.\n👈 **اختر الجودة للنشر:**", reply_markup=btns, quote=True)

# 4. عند اختيار الجودة (النشر)
@app.on_callback_query(filters.regex("^q_"))
async def on_pub(c, q):
    _, qual, r_id = q.data.split("_")
    r_id = int(r_id)
    
    if r_id in data_store:
        d = data_store[r_id]
        user = (await c.get_me()).username
        link = f"https://t.me/{user}?start={d['v_id']}"
        cap = f"🎬 {d['t']}\n🔹 الحلقة: {d['ep']}\n✨ الجودة: {qual}\n\n📥 [مشاهدة الآن]({link})"
        
        await c.send_photo(os.environ.get("PUBLIC_CHANNEL"), d['p'], cap,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=link)]]))
        await q.message.edit_text("🚀 تم النشر بنجاح!")
        data_store.pop(r_id, None)

app.run()
