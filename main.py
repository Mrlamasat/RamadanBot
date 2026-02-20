import os
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- الإعدادات ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")
DB_PATH = "bot_data.db"

app = Client("SimpleSqliteBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# دالة لإنشاء الجدول باستخدام sqlite3 العادي
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS movies 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, 
              v_file_id TEXT, 
              p_file_id TEXT, 
              caption TEXT, 
              quality TEXT)''')
    conn.commit()
    conn.close()

# 1. استقبال الفيديو
@app.on_message(filters.private & (filters.video | filters.document))
async def on_video(c, m):
    v_file_id = m.video.file_id if m.video else m.document.file_id
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("INSERT INTO movies (v_file_id) VALUES (?)", (v_file_id,))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    await m.reply_text(
        f"✅ تم تسجيل الفيديو (ID: {row_id})\n"
        "🖼 **الآن رد على هذه الرسالة بالبوستر والوصف.**",
        quote=True
    )

# 2. استقبال البوستر
@app.on_message(filters.private & filters.photo & filters.reply)
async def on_poster(c, m):
    try:
        row_id = int(m.reply_to_message.text.split("(ID: ")[1].split(")")[0])
    except:
        return await m.reply_text("⚠️ يرجى الرد على رسالة تأكيد الفيديو.")

    p_file_id = m.photo.file_id
    caption = m.caption or "بدون عنوان"

    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE movies SET p_file_id = ?, caption = ? WHERE id = ?", 
                 (p_file_id, caption, row_id))
    conn.commit()
    conn.close()

    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ HD", callback_data=f"st_{row_id}_HD"),
         InlineKeyboardButton("🌟 4K", callback_data=f"st_{row_id}_4K")]
    ])
    await m.reply_text("🖼 تم حفظ البوستر.\n👈 اختر الجودة للنشر:", reply_markup=btns)

# 3. النشر النهائي
@app.on_callback_query(filters.regex("^st_"))
async def finalize_publish(c, q):
    _, row_id, qual = q.data.split("_")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT v_file_id, p_file_id, caption FROM movies WHERE id = ?", (row_id,))
    row = cursor.fetchone()
    
    if row:
        v_file, p_file, desc = row
        conn.execute("UPDATE movies SET quality = ? WHERE id = ?", (qual, row_id))
        conn.commit()
        conn.close()

        bot = await c.get_me()
        link = f"https://t.me/{bot.username}?start={row_id}"
        
        final_caption = f"🎬 {desc}\n✨ الجودة: {qual}\n\n📥 اضغط للمشاهدة"
        
        await c.send_photo(
            PUBLIC_CHANNEL,
            photo=p_file,
            caption=final_caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=link)]])
        )
        await q.message.edit_text(f"🚀 تم النشر بنجاح بجودة {qual}!")
    else:
        conn.close()
        await q.message.edit_text("❌ لم يتم العثور على البيانات.")

# 4. تشغيل الفيديو للمشتركين
@app.on_message(filters.command("start") & filters.private)
async def start_handler(c, m):
    if len(m.command) > 1:
        row_id = m.command[1]
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute("SELECT v_file_id FROM movies WHERE id = ?", (row_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            await c.send_video(m.chat.id, video=row[0], caption="مشاهدة ممتعة!")
        else:
            await m.reply_text("❌ الملف غير موجود.")
    else:
        await m.reply_text("أهلاً يا محمد، أرسل فيديو للبدء.")

if __name__ == "__main__":
    init_db() # إنشاء القاعدة عند التشغيل
    app.run()
