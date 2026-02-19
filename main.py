import os
import asyncio
import asyncpg
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ================= إعداد المتغيرات =================
def get_env_int(name):
    val = os.getenv(name)
    if not val:
        raise ValueError(f"❌ {name} مفقود!")
    return int(val)

API_ID = get_env_int("API_ID")
API_HASH = os.getenv("API_HASH") or ""
BOT_TOKEN = os.getenv("BOT_TOKEN") or ""
CHANNEL_ID = get_env_int("CHANNEL_ID")
PUBLIC_CHANNEL = os.getenv("PUBLIC_CHANNEL", "").replace("@", "")
DATABASE_URL = os.getenv("DATABASE_URL") or ""
ADMINS = [int(x.strip()) for x in os.getenv("ADMINS", "").split(",") if x.strip()]

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app = Client("RamadanBot_Ultimate", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_pool = None

# ================= تهيئة قاعدة البيانات =================
async def init_db():
    global db_pool
    if not DATABASE_URL:
        print("⚠️ DATABASE_URL غير موجود، سيتم تشغيل البوت بدون قاعدة بيانات")
        return
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users(user_id BIGINT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS videos(
                telegram_id BIGINT PRIMARY KEY,
                title TEXT,
                duration TEXT,
                quality TEXT
            );
        """)
    print("✅ قاعدة البيانات متصلة والخدمة جاهزة.")

# ================= التحقق من الاشتراك =================
async def check_subscribe(client, user_id):
    if not PUBLIC_CHANNEL:
        return True
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        return True
    except UserNotParticipant:
        return False
    except:
        return True  # السماح في حال خطأ تقني

# ================= معالجة أمر /start =================
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id

    # تسجيل المستخدم
    if db_pool:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users(user_id) VALUES($1) ON CONFLICT DO NOTHING", user_id
            )

    # التحقق من الاشتراك الإجباري
    if not await check_subscribe(client, user_id):
        btn = [[InlineKeyboardButton("📢 اشترك في القناة أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")]]
        return await message.reply_text(
            "⚠️ يجب الاشتراك في القناة أولاً لتتمكن من استخدام الخدمة.",
            reply_markup=InlineKeyboardMarkup(btn)
        )

    if len(message.command) < 2:
        return await message.reply_text("أهلاً 👋\nأرسل رابط الحلقة أو رقم الفيديو للمشاهدة.")

    try:
        v_id = int(message.command[1])
    except:
        return await message.reply_text("❌ الرابط أو الرقم غير صحيح.")

    # محاولة جلب بيانات الفيديو من القاعدة
    video_info = None
    if db_pool:
        async with db_pool.acquire() as conn:
            video_info = await conn.fetchrow(
                "SELECT * FROM videos WHERE telegram_id=$1", v_id
            )

    caption = "🎬 **مشاهدة ممتعة!**"
    if video_info:
        caption = (
            f"🎬 **الاسم:** {video_info['title']}\n"
            f"⏱ **المدة:** {video_info['duration'] or 'غير معروف'}\n"
            f"📺 **الجودة:** {video_info['quality'] or 'HD'}"
        )

    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=CHANNEL_ID,
            message_id=v_id,
            caption=caption
        )
    except:
        await message.reply_text(
            "❌ عذراً، هذه الحلقة غير متوفرة حالياً.\n"
            "تأكد أن الفيديو موجود في القناة الخاصة."
        )

# ================= تسجيل الفيديوهات الجديدة تلقائياً =================
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def auto_register_video(client, m):
    title = m.caption or "حلقة جديدة"
    duration_sec = m.video.duration if m.video else 0
    mins, secs = divmod(duration_sec, 60)
    d_text = f"{mins}:{secs:02d}"
    quality = "HD"
    if m.video and m.video.height:
        quality = f"{m.video.height}p"

    if db_pool:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO videos(telegram_id, title, duration, quality) "
                "VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING",
                m.id, title, d_text, quality
            )

    bot_username = (await client.get_me()).username
    await m.reply_text(
        f"✅ تم تسجيل الفيديو!\n"
        f"🎬 {title}\n"
        f"⏱ {d_text}\n"
        f"📺 {quality}\n"
        f"🔗 https://t.me/{bot_username}?start={m.id}"
    )

# ================= إحصائيات البوت =================
@app.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client, message):
    if not db_pool:
        return await message.reply_text("📊 القاعدة غير متصلة حالياً.")
    async with db_pool.acquire() as conn:
        u_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        v_count = await conn.fetchval("SELECT COUNT(*) FROM videos")
    await message.reply_text(
        f"📊 إحصائيات البوت:\n"
        f"👥 المشتركين: {u_count}\n"
        f"🎬 الحلقات: {v_count}"
    )

# ================= التشغيل الرئيسي =================
async def main():
    await init_db()
    await app.start()
    me = await app.get_me()
    print(f"🚀 البوت يعمل الآن: @{me.username}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
