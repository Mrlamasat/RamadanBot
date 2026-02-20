import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية (تُجلب من إعدادات Railway) =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "").replace("@", "")

app = Client("MohammedSmartBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== دالة تهيئة قاعدة البيانات وإصلاح الأعمدة الناقصة =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    
    # إنشاء الجدول الأساسي إذا لم يكن موجوداً
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, title TEXT, 
                       poster_id TEXT, status TEXT)''')
    
    # إنشاء جدول الاشتراكات إذا لم يكن موجوداً
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                      (user_id INTEGER, poster_id TEXT, UNIQUE(user_id, poster_id))''')
    
    # فحص الأعمدة وإضافة الناقص منها (لحل مشكلة الخطأ السابق)
    cursor.execute("PRAGMA table_info(videos)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "duration" not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN duration TEXT")
        logging.info("✅ تم إضافة عمود duration")
    
    if "title" not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN title TEXT")
        logging.info("✅ تم إضافة عمود title")

    if "ep_num" not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN ep_num INTEGER")
        logging.info("✅ تم إضافة عمود ep_num")
    
    if "poster_file_id" not in columns:
        cursor.execute("ALTER TABLE videos ADD COLUMN poster_file_id TEXT")
        logging.info("✅ تم إضافة عمود poster_file_id")

    conn.commit()
    conn.close()

# تشغيل التهيئة عند بدء الكود
init_db()

def db_execute(query, params=(), fetch=True):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    res = cursor.fetchall() if fetch else None
    conn.close()
    return res

def format_duration(seconds):
    if not seconds: return "غير متوفر"
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d} دقيقة"

# ===== استقبال المحتوى (نظام الربط التلقائي) =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration_str = format_duration(duration_sec)
    
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
               (str(message.id), duration_str, "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {message.id})\nالآن أرسل **البوستر (الصورة)** لهذا الفيديو.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, poster_file_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (message.caption or "حلقة جديدة", message.photo.file_id, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم ربط البوستر.\nالآن أرسل **رقم الحلقة** (أرقام فقط):")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start", "edit", "list"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("HD 720p", callback_data=f"q_HD_{v_id}"),
         InlineKeyboardButton("SD 480p", callback_data=f"q_SD_{v_id}")]
    ])
    await message.reply_text(f"✅ تم تسجيل الحلقة {message.text}.\nاختر الجودة للنشر في القناة العامة:", reply_markup=markup)

@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, p_id = res[0]
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    caption_text = (f"🎬 **{title}**\n\n"
                    f"🔢 رقم الحلقة: {db_execute('SELECT ep_num FROM videos WHERE v_id=?', (v_id,))[0][0]}\n"
                    f"⏱ المدة: {duration}\n"
                    f"✨ الجودة: {quality}\n\n"
                    f"📥 [اضغط هنا للمشاهدة الآن]({link})")
    
    await client.send_photo(f"@{PUBLIC_CHANNEL}", photo=p_id, caption=caption_text,
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
    await query.message.edit_text("✅ تم النشر بنجاح في القناة العامة!")

# ===== نظام الـ Start للمشتركين =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت المسلسلات! 🌙")
        return

    v_id = message.command[1]
    try:
        # التحقق من الاشتراك الإجباري
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", message.from_user.id)
        
        # إرسال الفيديو من قناة التخزين
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)
        
        # عرض قائمة الحلقات الأخرى لنفس المسلسل (إذا وجد بوستر مشترك)
        video_data = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if video_data and video_data[0][0]:
            p_id = video_data[0][0]
            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC", (p_id,))
            if len(all_ep) > 1:
                btns = []
                row = []
                bot_info = await client.get_me()
                for v_id_item, num in all_ep:
                    label = f"الحلقة {num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id_item}"))
                    if len(row) == 2:
                        btns.append(row)
                        row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي حلقات المسلسل:", reply_markup=InlineKeyboardMarkup(btns))

    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك، أرسل الفيديو", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً لمشاهدة الفيديو.", reply_markup=InlineKeyboardMarkup(btn))
    except Exception as e:
        await message.reply_text("❌ حدث خطأ، تأكد من أن الفيديو موجود في قناة التخزين.")

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub_callback(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(f"@{PUBLIC_CHANNEL}", query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await query.answer("⚠️ لم تشترك بعد!", show_alert=True)

print("🚀 البوت يعمل الآن بنجاح...")
app.run()

init_db()

def db_execute(query, params=(), fetch=True):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    res = cursor.fetchall() if fetch else None
    conn.close()
    return res

def format_duration(seconds):
    if not seconds: return "00:00"
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d} دقيقة"

# ===== استقبال المحتوى (نظام الربط) =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
               (str(message.id), format_duration(duration), "waiting"), fetch=False)
    await message.reply_text(f"✅ تم ربط الفيديو (ID: {message.id})\nأرسل البوستر الآن.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET title = ?, poster_id = ?, status = 'awaiting_ep' WHERE v_id = ?",
               (message.caption or "حلقة جديدة", message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم استلام البوستر.\n🔢 أرسل الآن رقم الحلقة (أرقام فقط):")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start", "edit", "list"]))
async def receive_ep_number(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status = 'awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res or not message.text.isdigit(): return
    
    v_id = res[0][0]
    db_execute("UPDATE videos SET ep_num = ?, status = 'ready_quality' WHERE v_id = ?", (int(message.text), v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
         InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}"),
         InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}")]
    ])
    await message.reply_text(f"✅ تم حفظ الحلقة رقم: {message.text}\nاختر الجودة للنشر في القناة:", reply_markup=markup)

@app.on_callback_query(filters.regex(r"^q_"))
async def quality_callback(client, query):
    _, quality, v_id = query.data.split("_")
    res = db_execute("SELECT duration, title, poster_id FROM videos WHERE v_id = ?", (v_id,))
    if not res: return
    duration, title, p_id = res[0]
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    await client.send_photo(CHANNEL_ID, photo=p_id,
                           caption=f"🎬 **حلقة جديدة جاهزة**\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 [مشاهدة الآن]({link})",
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
    
    db_execute("UPDATE videos SET status = 'posted' WHERE v_id = ?", (v_id,), fetch=False)
    
    # إشعارات المشتركين
    subscribers = db_execute("SELECT user_id FROM subscriptions WHERE poster_id = ?", (p_id,))
    for sub in subscribers:
        try:
            await client.send_message(sub[0], f"🔔 **تحديث جديد!**\nتم إضافة حلقة جديدة للمسلسل الذي تتابعه 🎬.\n📥 [اضغط هنا للمشاهدة الآن]({link})", disable_web_page_preview=True)
        except: pass
    await query.message.delete()

# ===== نظام الـ Start (يدعم القديم والجديد) =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}!")
        return

    v_id = message.command[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, message.from_user.id)
        
        try:
            channel_msg = await client.get_messages(CHANNEL_ID, int(v_id))
            if not channel_msg or channel_msg.empty:
                await message.reply_text("❌ الفيديو غير موجود.")
                return
        except:
            await message.reply_text("❌ خطأ في الوصول للفيديو.")
            return

        video_data = db_execute("SELECT poster_id, title, ep_num FROM videos WHERE v_id = ?", (v_id,))

        # منطق التسجيل التلقائي للفيديوهات القديمة
        if not video_data:
            duration = format_duration(channel_msg.video.duration) if channel_msg.video else "غير معروف"
            db_execute("INSERT OR IGNORE INTO videos (v_id, duration, title, status) VALUES (?, ?, ?, ?)",
                       (v_id, duration, "فيديو قديم", "posted"), fetch=False)
            video_data = db_execute("SELECT poster_id, title, ep_num FROM videos WHERE v_id = ?", (v_id,))

        # إرسال الفيديو (محمي من الحفظ/التحويل)
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

        # عرض قائمة الحلقات
        if video_data and video_data[0][0]:
            p_id, title, ep_num = video_data[0]
            db_execute("INSERT OR IGNORE INTO subscriptions (user_id, poster_id) VALUES (?, ?)", (message.from_user.id, p_id), fetch=False)

            all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY COALESCE(ep_num, rowid) ASC", (p_id,))
            
            if len(all_ep) > 1:
                btns = []; row = []
                bot_info = await client.get_me()
                for i, (v_id_item, num) in enumerate(all_ep, 1):
                    display_num = num if num else i
                    label = f"▶️ الحلقة {display_num}" if v_id_item == v_id else f"الحلقة {display_num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id_item}"))
                    if len(row) == 2: btns.append(row); row = []
                if row: btns.append(row)

                msg_text = "📺 شاهد المزيد من الحلقات:" if len(all_ep) > 10 else "📺 باقي حلقات المسلسل:"
                await message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(btns))

    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 اشترك أولاً", url=f"https://t.me/{PUBLIC_CHANNEL}")],
               [InlineKeyboardButton("✅ تم الاشتراك", callback_data=f"chk_{v_id}")]]
        await message.reply_text("⚠️ اشترك بالقناة لتفعيل الرابط.", reply_markup=InlineKeyboardMarkup(btn))

# ===== الأوامر الإدارية =====
@app.on_message(filters.command("edit") & filters.private)
async def edit_title(client, message):
    if len(message.command) < 3: return
    if message.command[1].lower() == "all":
        res = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (message.command[2],))
        if res:
            db_execute("UPDATE videos SET title = ? WHERE poster_id = ?", (" ".join(message.command[3:]), res[0][0]), fetch=False)
            await message.reply_text("✅ تم تحديث اسم المسلسل لجميع الحلقات.")
    else:
        db_execute("UPDATE videos SET title = ? WHERE v_id = ?", (" ".join(message.command[2:]), message.command[1]), fetch=False)
        await message.reply_text("✅ تم تحديث العنوان.")

@app.on_callback_query(filters.regex(r"^chk_"))
async def check_sub(client, query):
    v_id = query.data.split("_")[1]
    try:
        await client.get_chat_member(PUBLIC_CHANNEL, query.from_user.id)
        await query.message.delete()
        await client.copy_message(query.from_user.id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await query.answer("⚠️ اشترك أولاً!", show_alert=True)

app.run()
