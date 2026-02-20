@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    try:
        user_id = message.from_user.id
        first_name = message.from_user.first_name or "صديق"

        # حالة /start فقط بدون v_id
        if len(message.command) == 1:
            await message.reply_text(f"أهلاً بك يا {first_name} في بوت المسلسلات! 🌙\n\n"
                                     f"أرسل /start <رقم_الحلقة> لمشاهدة حلقة محددة.")
            return

        # حالة /start مع v_id
        v_id = message.command[1]

        # التحقق من الاشتراك الإجباري
        try:
            await client.get_chat_member(f"@{PUBLIC_CHANNEL}", user_id)
        except UserNotParticipant:
            # المستخدم لم يشترك بعد
            btn = [
                [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{PUBLIC_CHANNEL}")],
                [InlineKeyboardButton("✅ تم الاشتراك، أرسل الفيديو", callback_data=f"chk_{v_id}")]
            ]
            await message.reply_text(
                "⚠️ يجب عليك الاشتراك في القناة أولاً لمشاهدة الفيديو.",
                reply_markup=InlineKeyboardMarkup(btn)
            )
            return

        # إرسال الفيديو من قناة التخزين
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id), protect_content=True)

        # عرض باقي الحلقات لنفس المسلسل
        video_data = db_execute("SELECT poster_id FROM videos WHERE v_id = ?", (v_id,))
        if video_data and video_data[0][0]:
            p_id = video_data[0][0]
            all_ep = db_execute(
                "SELECT v_id, ep_num FROM videos WHERE poster_id = ? AND status = 'posted' ORDER BY ep_num ASC",
                (p_id,)
            )
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

    except Exception as e:
        # تسجيل كامل للخطأ في السجل
        logging.exception(f"❌ خطأ في /start: {e}")
        # إرسال رسالة للمستخدم حتى لو حصل خطأ
        await message.reply_text(f"❌ حدث خطأ أثناء معالجة /start.\nالرجاء المحاولة لاحقاً.")
