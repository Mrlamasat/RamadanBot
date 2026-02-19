import os
import asyncio
import asyncpg
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- إعداد المتغيرات من ريلوي ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")
# جلب قائمة المديرين وتنظيفها
ADMINS = [int(x.strip()) for x in os.getenv("ADMINS", "").split(",") if x.strip()]

# تصحيح رابط قاعدة البيانات ليتوافق مع مكتبة asyncpg
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app = Client("RamadanBot_Final_Fixed", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_pool = None

# --- تهيئة قاعدة البيانات ---
async def init_db():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users(user_id BIGINT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS videos(telegram_id BIGINT PRIMARY KEY, title TEXT);
            """)
        print("✅ قاعدة البيانات متصلة والخدمة جاهزة.")
    except Exception as e:
        print(f"⚠️ تحذير: فشل الاتصال بالقاعدة، سيعمل البوت بنظام النسخ المباشر: {e}")

# --- معالجة الأوامر ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # تسجيل المستخدم في القاعدة (إذا كانت متصلة)
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute("INSERT INTO users(user_id) VALUES($1) ON CONFLICT DO NOTHING", user_id)
        except: pass

    # إذا أرسل المستخدم /start بدون أرقام
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محسن 👋\nأرسل رابط الحلقة للمشاهدة.")

    # محاولة استخراج رقم الحلقة (ID)
    try:
        v_id = int(message.command[1])
    except:
        return await message.reply_text("❌ الرابط غير صحيح.")

    # --- الحل المنقذ للروابط القديمة والجديدة ---
    # البوت سيحاول نسخ الرسالة مباشرة من القناة باستخدام الرقم الموجود في الرابط
    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=CHANNEL_ID,
            message_id=v_id,
            caption="🎬 **مشاهدة ممتعة!**"
        )
    except Exception as e:
        # إذا فشل، فهذا يعني أن الرقم غير موجود في القناة أو البوت ليس مديراً هناك
        await message.reply_text("❌ عذراً، هذه الحلقة غير متوفرة حالياً.\nتأكد أن الفيديو ما زال موجوداً في القناة الخاصة.")

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def auto_register_video(client, m):
    # تسجيل الفيديو الجديد في القاعدة عند رفعه في القناة
    title = m.caption or "حلقة جديدة"
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute("INSERT INTO videos(telegram_id, title) VALUES($1, $2) ON CONFLICT DO NOTHING", m.id, title)
        except: pass
    await m.reply_text(f"✅ تم تسجيل الفيديو بنجاح!\n🔗 الرابط: `https://t.me/{(await client.get_me()).username}?start={m.id}`")

@app.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client, message):
    if not db_pool:
        return await message.reply_text("📊 القاعدة غير متصلة حالياً.")
    async with db_pool.acquire() as conn:
        u_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        v_count = await conn.fetchval("SELECT COUNT(*) FROM videos")
    await message.reply_text(f"📊 الإحصائيات:\n👥 المشتركين: {u_count}\n🎬 الحلقات المسجلة: {v_count}")

# --- التشغيل ---
async def main():
    await init_db()
    await app.start()
    me = await app.get_me()
    print(f"🚀 البوت يعمل الآن تحت معرف: @{me.username}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
