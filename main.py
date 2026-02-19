import os
import asyncio
import asyncpg
from pyrogram import Client, filters

# استلام المتغيرات الأساسية
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# تصحيح رابط قاعدة البيانات فوراً
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app = Client("RamadanBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_pool = None

async def init_db():
    global db_pool
    try:
        # إنشاء اتصال قوي بقاعدة البيانات
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
        async with db_pool.acquire() as conn:
            await conn.execute("CREATE TABLE IF NOT EXISTS users(user_id BIGINT PRIMARY KEY);")
        print("✅ قاعدة البيانات متصلة وجاهزة.")
    except Exception as e:
        print(f"⚠️ فشل الاتصال بالقاعدة (سيعمل البوت بدونها حالياً): {e}")

@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    
    # محاولة تسجيل المستخدم في القاعدة بهدوء
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute("INSERT INTO users(user_id) VALUES($1) ON CONFLICT DO NOTHING", user_id)
        except:
            pass
            
    await message.reply_text(f"أهلاً بك يا محسن 👋\nالبوت متصل بقاعدة البيانات وجاهز للعمل!")

async def start_bot():
    await init_db()
    await app.start()
    print("🚀 البوت بدأ العمل الآن...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_bot())
