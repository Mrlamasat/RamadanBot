import os
import asyncio
import logging
import asyncpg
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية (مع حماية للقيم) =====
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app = Client("RamadanBot_Final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_pool = None

# ===== تهيئة قاعدة البيانات =====
async def init_db():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users(user_id BIGINT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS videos(v_id TEXT PRIMARY KEY, title TEXT, duration TEXT, quality TEXT);
            """)
        logging.info("✅ قاعدة البيانات جاهزة")
    except Exception as e:
        logging.error(f"❌ خطأ قاعدة البيانات: {e}")

# ===== نظام العمل المبسط (بدون الحاجة لصور خارجية حالياً) =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, m):
    if len(m.command) < 2:
        return await m.reply_text("أهلاً بك يا محمد! أرسل رابط الحلقة للمشاهدة.")
    
    v_id = m.command[1]
    
    # تحقق الاشتراك
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, m.from_user.id)
    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")]]
        return await m.reply_text("⚠️ يجب الاشتراك لمشاهدة الحلقة.", reply_markup=InlineKeyboardMarkup(btn))
    except: pass

    try:
        await client.copy_message(m.chat.id, CHANNEL_ID, int(v_id))
    except:
        await m.reply_text("❌ الحلقة غير متوفرة.")

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def auto_reg(client, m):
    bot_me = await client.get_me()
    link = f"https://t.me/{bot_me.username}?start={m.id}"
    await m.reply_text(f"✅ تم تسجيل الحلقة!\n🔗 الرابط: {link}")

async def main():
    await init_db()
    await app.start()
    logging.info("🚀 البوت انطلق بنجاح!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
