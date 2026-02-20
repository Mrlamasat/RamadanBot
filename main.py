import os
import aiosqlite
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

class VideoBot:
    def __init__(self, client):
        self.client = client

    async def init_db(self):
        async with aiosqlite.connect("bot_data.db") as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    v_id TEXT PRIMARY KEY,
                    duration INTEGER,
                    poster_id TEXT,
                    status TEXT,
                    ep_num INTEGER,
                    quality TEXT,
                    user_id INTEGER
                )
            ''')
            await db.commit()

    async def db_execute(self, query, params=(), fetch=True):
        async with aiosqlite.connect("bot_data.db") as db:
            cursor = await db.execute(query, params)
            if fetch:
                rows = await cursor.fetchall()
            else:
                rows = None
            await db.commit()
            return rows

    def format_duration(self, seconds):
        if not seconds: return "غير محدد"
        mins, secs = divmod(seconds, 60)
        return f"{mins}:{secs:02d} دقيقة"

    # 1. استقبال الفيديو
    async def receive_video(self, client, message):
        v_id = str(message.id)
        duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)

        await self.db_execute(
            "INSERT OR REPLACE INTO videos (v_id, duration, status, user_id) VALUES (?, ?, ?, ?)",
            (v_id, duration_sec, "waiting_poster", message.from_user.id),
            fetch=False
        )
        await message.reply_text("✅ تم استلام الفيديو.\n🖼 الآن أرسل **البوستر** (صورة فقط):")

    # 2. استقبال البوستر
    async def receive_poster(self, client, message):
        res = await self.db_execute(
            "SELECT v_id FROM videos WHERE status='waiting_poster' AND user_id=? ORDER BY rowid DESC LIMIT 1",
            (message.from_user.id,)
        )
        if not res: return
        
        v_id = res[0][0]
        await self.db_execute(
            "UPDATE videos SET poster_id=?, status='awaiting_ep' WHERE v_id=?",
            (message.photo.file_id, v_id),
            fetch=False
        )
        await message.reply_text("🖼 تم حفظ البوستر.\n🔢 أرسل الآن **رقم الحلقة**:")

    # 3. استلام رقم الحلقة وعرض الجودات
    async def receive_ep_number(self, client, message):
        if not message.text.isdigit(): return
        
        res = await self.db_execute(
            "SELECT v_id FROM videos WHERE status='awaiting_ep' AND user_id=? ORDER BY rowid DESC LIMIT 1",
            (message.from_user.id,)
        )
        if not res: return
        
        v_id = res[0][0]
        ep_num = int(message.text)

        await self.db_execute(
            "UPDATE videos SET ep_num=?, status='waiting_quality' WHERE v_id=?",
            (ep_num, v_id),
            fetch=False
        )

        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("SD", callback_data=f"p_SD_{v_id}"),
                InlineKeyboardButton("HD", callback_data=f"p_HD_{v_id}"),
                InlineKeyboardButton("4K", callback_data=f"p_4K_{v_id}")
            ]
        ])
        await message.reply_text(f"✅ تم تحديد الحلقة {ep_num}.\n✨ اختر الجودة المطلوبة للنشر:", reply_markup=markup)

    # 4. النشر النهائي عند اختيار الجودة
    async def publish_now(self, client, query):
        _, quality, v_id = query.data.split("_")
        res = await self.db_execute("SELECT ep_num, poster_id, duration FROM videos WHERE v_id=?", (v_id,))
        if not res:
            await query.answer("❌ خطأ في البيانات", show_alert=True)
            return
            
        ep_num, poster_id, duration = res[0]
        duration_str = self.format_duration(duration)
        bot_user = (await client.get_me()).username
        watch_link = f"https://t.me/{bot_user}?start={v_id}"

        caption = (f"🎬 **الحلقة {ep_num}**\n"
                   f"⏱ **المدة:** {duration_str}\n"
                   f"✨ **الجودة:** {quality}\n\n"
                   f"📥 اضغط الزر أدناه للمشاهدة")
        
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        
        try:
            # النشر كصورة (بوستر) في القناة العامة مع زر المشاهدة
            await client.send_photo(chat_id=f"@{PUBLIC_CHANNEL}", photo=poster_id, caption=caption, reply_markup=markup)
            await self.db_execute("UPDATE videos SET quality=?, status='posted' WHERE v_id=?", (quality, v_id), fetch=False)
            await query.message.edit_text(f"🚀 تم النشر بنجاح بجودة {quality}!")
        except Exception as e:
            await query.message.edit_text(f"❌ فشل النشر: {e}")

    # إرسال الفيديو للمستخدم (عند الضغط على start أو حلقة من القائمة)
    async def send_video_with_list(self, client, chat_id, v_id):
        res = await self.db_execute("SELECT poster_id, ep_num, duration, quality FROM videos WHERE v_id=?", (v_id,))
        if not res: return
        
        poster_id, ep_num, duration, quality = res[0]
        
        # جلب قائمة الحلقات لنفس المسلسل (بناءً على البوستر)
        all_eps = await self.db_execute(
            "SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC",
            (poster_id,)
        )

        buttons = []
        row = []
        for vid, num in all_eps:
            text = f"• {num} •" if vid == v_id else f"{num}"
            row.append(InlineKeyboardButton(text, callback_data=f"watch_{vid}"))
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row: buttons.append(row)

        caption = f"🎬 **الحلقة {ep_num}**\n⏱ **المدة:** {self.format_duration(duration)}\n✨ **الجودة:** {quality}"
        
        try:
            # إرسال الفيديو الفعلي من قناة التخزين
            await client.copy_message(chat_id, CHANNEL_ID, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await client.send_message(chat_id, "❌ عذراً، تعذر تحميل الحلقة.")

# =================== تشغيل وإدارة الحلقات ===================
bot = VideoBot(app)

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def handle_video(client, message):
    await bot.receive_video(client, message)

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def handle_poster(client, message):
    await bot.receive_poster(client, message)

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def handle_ep_number(client, message):
    await bot.handle_ep_number(client, message) # تصحيح استدعاء الدالة

@app.on_callback_query(filters.regex(r"^p_"))
async def handle_publish(client, query):
    await bot.publish_now(client, query)

@app.on_message(filters.command("start") & filters.private)
async def handle_start(client, message):
    await bot.init_db() # التأكد من إنشاء القاعدة
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد! أرسل رابط الحلقة للمشاهدة.")
        return
    
    v_id = message.command[1]
    # التحقق من الاشتراك الإجباري
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
    except UserNotParticipant:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{PUBLIC_CHANNEL}")],
            [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]
        ])
        await message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً لمشاهدة الحلقة.", reply_markup=markup)
        return
    
    await bot.send_video_with_list(client, message.chat.id, v_id)

@app.on_callback_query(filters.regex(r"^watch_"))
async def handle_watch(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await bot.send_video_with_list(client, query.from_user.id, v_id)

@app.on_callback_query(filters.regex(r"^chk_"))
async def handle_check(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, query.from_user.id)
        await query.message.delete()
        await bot.send_video_with_list(client, query.from_user.id, v_id)
    except UserNotParticipant:
        await query.answer("❌ لم تشترك بعد!", show_alert=True)

app.run()
