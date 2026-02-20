import os
import sqlite3
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, PeerIdInvalid

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية (تأكد من صحتها) =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
# ملاحظة: إذا كنت تستخدم User Session، اترك BOT_TOKEN فارغاً في الـ Client
SESSION_NAME = "user_session" 
CHANNEL_ID = -1003547072209  # تأكد أن الـ ID رقم صحيح (Integer) وليس نصاً

# تعريف الكلاينت كحساب مستخدم (User Session)
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

# ===== قاعدة البيانات =====
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

# ===== أمر الإصلاح القوي (باستخدام صلاحيات الحساب الشخصي) =====
@app.on_message(filters.command("fix_old_data") & filters.me) # filters.me لأنك تستخدم حسابك الشخصي
async def fix_old_data(client, message):
    msg_wait = await message.reply_text("🚀 جاري سحب البيانات بصلاحيات الحساب المساعد...")
    count_linked, count_videos = 0, 0
    
    try:
        # الحساب الشخصي لا يواجه مشكلة BOT_METHOD_INVALID
        async for msg in client.get_chat_history(CHANNEL_ID):
            try:
                is_video = msg.video or (msg.document and "video" in (msg.document.mime_type or ""))
                if is_video:
                    v_id = str(msg.id)
                    db_execute("INSERT OR IGNORE INTO videos (v_id, status) VALUES (?, ?)", (v_id, "posted"), fetch=False)
                    count_videos += 1

                    # البحث عن البوستر (الصورة)
                    async for search_msg in client.get_chat_history(CHANNEL_ID, limit=50, offset_id=msg.id):
                        if search_msg.photo:
                            p = search_msg.photo
                            db_execute("UPDATE videos SET poster_id=?, poster_file_id=?, status='posted' WHERE v_id=?",
                                       (p.file_unique_id, p.file_id, v_id), fetch=False)
                            count_linked += 1
                            break
                    
                    if count_videos % 20 == 0:
                        await msg_wait.edit(f"⏳ جاري الربط...\n🎬 فيديوهات: {count_videos}\n🖼 بوسترات: {count_linked}")
            
            except FloodWait as fw:
                await asyncio.sleep(fw.value) # هنا نستخدم .value بشكل صحيح مع كائن الخطأ
            except Exception:
                continue

        await msg_wait.edit(f"🏁 اكتمل الإصلاح بنجاح!\n🎬 تم فحص: `{count_videos}` فيديو\n🖼 تم ربط: `{count_linked}` بوستر")
    
    except Exception as e:
        await msg_wait.edit(f"❌ خطأ: `{str(e)}`")

app.run()
