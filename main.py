import os
import sqlite3
import aiosqlite
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- الإعدادات ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")
DB_PATH = "bot_data.db"

app = Client("DatabaseBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# دالة لإنشاء الجدول إذا لم يكن موجوداً
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS movies 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, 
              v_file_id TEXT, 
              p_file_id TEXT, 
              caption TEXT, 
              quality TEXT)''')
        await db.commit()

# 1. استقبال الفيديو
@app.on_message(filters.private & (filters.video | filters.document))
async def on_video(c, m):
    v_file_id = m.video.file_id if m.video else m.document.file_id
    # نفتح صف مؤقت في القاعدة ونخزن الـ file_id للفيديو
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("INSERT INTO movies (v_file_id) VALUES (?)", (v_file_id,))
        row_id = cursor.lastrowid
        await db.commit()
    
    await m.reply_text(
        f"✅ تم تسجيل الفيديو بنظامك (ID: {row_id})\n"
        "🖼 **رد على هذه الرسالة بالبوستر والوصف الآن.**",
        quote=True
    )

# 2. استقبال البوستر وتحديث قاعدة البيانات
@app.on_message(filters.private & filters.photo & filters.reply)
async def on_poster(c, m):
    # استخراج الـ ID من الرسالة المردود عليها (بناءً على نص البوت)
    try:
        row_id = int(m.reply_to_message.text.split("(ID: ")[1].split(")")[0])
    except:
        return await m.reply_text("⚠️ يرجى الرد على رسالة تأكيد الفيديو الصحيحة.")

    p_file_id = m.photo.file_id
    caption = m.caption or "بدون عنوان"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE movies SET p_file_id = ?, caption = ? WHERE id = ?", 
                         (p_file_id, caption, row_id))
        await db.commit()

    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ HD", callback_data=f"set_{row_id}_HD"),
         InlineKeyboardButton("🌟 4K", callback_data=f"set_{row_id}_4K")]
    ])
    await m.reply_text("🖼 تم حفظ البوستر والوصف.\n👈 اختر الجودة للنشر:", reply_markup=btns)

# 3. النشر النهائي من قاعدة البيانات
@app.on_callback_query(filters.regex("^set_"))
async def finalize_publish(c, q):
    _, row_id, qual = q.data.split("_")
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT v_file_id, p_file_id, caption FROM movies WHERE id = ?", (row_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                v_file, p_file, desc = row
                # تحديث الجودة في القاعدة
                await db.execute("UPDATE movies SET quality = ? WHERE id = ?", (qual, row_id))
                await db.commit()

                bot = await c.get_me()
                link = f"https://t.me/{bot.username}?start={row_id}"
                
                final_caption = f"🎬 {desc}\n✨ الجودة: {qual}\n\n📥 اضغط للمشاهدة"
                
                await c.send_photo(
                    PUBLIC_CHANNEL,
                    photo=p_file,
                    caption=final_caption,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=link)]])
                )
                await q.message.edit_text("🚀 تم النشر بنجاح من قاعدة البيانات!")

# 4. معالجة رابط المشاهدة (استرجاع الفيديو بـ file_id)
@app.on_message(filters.command("start") & filters.private)
async def start_handler(c, m):
    if len(m.command) > 1:
        row_id = m.command[1]
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT v_file_id FROM movies WHERE id = ?", (row_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    # إرسال الفيديو باستخدام الـ file_id المخزن (أسرع وأضمن)
                    await c.send_video(m.chat.id, video=row[0], caption="مشاهدة ممتعة!")
                else:
                    await m.reply_text("❌ الملف غير موجود في قاعدة البيانات.")
    else:
        await m.reply_text("أهلاً يا محمد، أرسل فيديو للبدء.")

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    app.run()
