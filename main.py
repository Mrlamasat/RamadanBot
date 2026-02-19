import os
import asyncio
import asyncpg
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعداد المتغيرات
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")
ADMINS = [int(x.strip()) for x in os.getenv("ADMINS", "").split(",") if x.strip()]

# تصحيح الرابط لـ Railway
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app = Client("RamadanBot_Final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS series(id SERIAL PRIMARY KEY, poster_uid TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS videos(id SERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE, series_id INT REFERENCES series(id), title TEXT);
            CREATE TABLE IF NOT EXISTS users(user_id BIGINT PRIMARY KEY);
        """)

# --- معالجة الرسائل ---

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    # تسجيل المستخدم
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO users(user_id) VALUES($1) ON CONFLICT DO NOTHING", user_id)
    
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك في بوت الحلقات! أرسل رابط الحلقة للمشاهدة.")

    # جلب الحلقة
    v_id = int(message.command[1])
    async with db_pool.acquire() as conn:
        video = await conn.fetchrow("SELECT * FROM videos WHERE telegram_id=$1", v_id)
    
    if video:
        await client.copy_message(message.chat.id, CHANNEL_ID, v_id, caption=f"🎬 **{video['title']}**")
    else:
        await message.reply_text("❌ المعذرة، هذه الحلقة غير موجودة.")

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def save_video(client, m):
    title = m.caption or "حلقة جديدة"
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO videos(telegram_id, title) VALUES($1, $2) ON CONFLICT DO NOTHING", m.id, title)
    await m.reply_text(f"✅ تم تسجيل الفيديو بنجاح (ID: {m.id})")

@app.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats(client, message):
    async with db_pool.acquire() as conn:
        u_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        v_count = await conn.fetchval("SELECT COUNT(*) FROM videos")
    await message.reply_text(f"📊 الإحصائيات:\n👥 مستخدمين: {u_count}\n🎬 حلقات: {v_count}")

async def main():
    await init_db()
    await app.start()
    print("🚀 البوت جاهز تماماً الآن!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
