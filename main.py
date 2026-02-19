import os
import logging
import asyncio
import asyncpg
from time import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait, UserIsBlocked

# ================= إعدادات البيئة =================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
PUBLIC_CHANNEL = os.getenv("PUBLIC_CHANNEL", "").replace("@", "")
DATABASE_URL = os.getenv("DATABASE_URL")
# جلب قائمة الإدمن وتنظيفها من أي مسافات
ADMINS = [int(x.strip()) for x in os.getenv("ADMINS", "").split(",") if x.strip()]

app = Client("ProBot_Fixed", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

db = None
BOT_USERNAME = None
cooldowns = {}

# ================= إعداد قاعدة البيانات =================
async def init_db():
    async with db.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS series(id SERIAL PRIMARY KEY, poster_uid TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS videos(id SERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE, series_id INT REFERENCES series(id), title TEXT, duration TEXT);
            CREATE TABLE IF NOT EXISTS users(user_id BIGINT PRIMARY KEY);
        """)

# ================= نظام التنبيهات والخدمات =================
async def notify_users(title, v_id):
    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
    link = f"https://t.me/{BOT_USERNAME}?start={v_id}"
    text = f"🌟 **حلقة جديدة متوفرة الآن!**\n🎬 **الاسم:** {title}\n👇 اضغط للمشاهدة:"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ شاهد الآن", url=link)]])
    for row in rows:
        try:
            await app.send_message(row["user_id"], text, reply_markup=markup)
            await asyncio.sleep(0.05)
        except FloodWait as e: await asyncio.sleep(e.value)
        except Exception: continue

async def get_series_buttons(series_id, current_v_id):
    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT telegram_id FROM videos WHERE series_id=$1 ORDER BY id ASC", series_id)
    buttons, row = [], []
    for i, r in enumerate(rows, 1):
        v_id = r["telegram_id"]
        txt = f"✅ {i}" if v_id == current_v_id else f"{i}"
        row.append(InlineKeyboardButton(txt, url=f"https://t.me/{BOT_USERNAME}?start={v_id}"))
        if len(row) == 5: buttons.append(row); row = []
    if row: buttons.append(row)
    return buttons

# ================= المعالجات (Handlers) =================
@app.on_message(filters.service, group=1)
async def delete_service(_, m):
    try: await m.delete()
    except: pass

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def on_video(client, m):
    duration = m.video.duration if m.video else 0
    d_text = f"{duration // 60}:{duration % 60:02d}"
    title = m.caption or "حلقة جديدة"
    async with db.acquire() as conn:
        await conn.execute("INSERT INTO videos(telegram_id, title, duration) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", m.id, title, d_text)
    await m.reply_text(f"✅ تم تسجيل الفيديو {m.id}. أرسل البوستر الآن.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def on_photo(client, m):
    async with db.acquire() as conn:
        series = await conn.fetchrow("INSERT INTO series(poster_uid) VALUES($1) ON CONFLICT (poster_uid) DO UPDATE SET poster_uid=EXCLUDED.poster_uid RETURNING id", m.photo.file_unique_id)
        video = await conn.fetchrow("SELECT telegram_id, title FROM videos WHERE series_id IS NULL ORDER BY id DESC LIMIT 1")
        if not video: return await m.reply_text("❌ أرسل الفيديو أولاً.")
        await conn.execute("UPDATE videos SET series_id=$1 WHERE telegram_id=$2", series["id"], video["telegram_id"])
    asyncio.create_task(notify_users(video["title"], video["telegram_id"]))
    await m.reply_text(f"🔗 تم الربط بنجاح!")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    if user_id in cooldowns and time() - cooldowns[user_id] < 2: return
    cooldowns[user_id] = time()

    # تسجيل المستخدم
    try:
        async with db.acquire() as conn:
            await conn.execute("INSERT INTO users(user_id) VALUES($1) ON CONFLICT DO NOTHING", user_id)
    except: pass

    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا محسن! أرسل رابط الحلقة للمشاهدة.")

    v_id = int(message.command[1])
    if PUBLIC_CHANNEL:
        try:
            await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        except UserNotParticipant:
            return await message.reply_text("⚠️ اشترك في القناة أولاً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{PUBLIC_CHANNEL}")]]))

    async with db.acquire() as conn:
        video = await conn.fetchrow("SELECT * FROM videos WHERE telegram_id=$1", v_id)
    if not video: return await message.reply_text("❌ الحلقة غير متوفرة.")

    nav = await get_series_buttons(video["series_id"], v_id)
    await client.copy_message(message.chat.id, CHANNEL_ID, v_id, caption=f"🎬 **{video['title']}**", reply_markup=InlineKeyboardMarkup(nav) if nav else None)

@app.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client, message):
    async with db.acquire() as conn:
        users = await conn.fetchval("SELECT COUNT(*) FROM users")
        videos = await conn.fetchval("SELECT COUNT(*) FROM videos")
    await message.reply_text(f"📊 الإحصائيات:\n👥 المستخدمين: {users}\n🎬 الحلقات: {videos}")

# ================= التشغيل الرئيسي =================
async def main():
    global db, BOT_USERNAME
    # تصحيح رابط القاعدة لـ Railway
    final_db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL.startswith("postgres://") else DATABASE_URL
    
    db = await asyncpg.create_pool(final_db_url, min_size=1, max_size=10)
    await init_db()
    await app.start()
    me = await app.get_me()
    BOT_USERNAME = me.username
    logging.info(f"🚀 البوت يعمل: @{BOT_USERNAME}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
