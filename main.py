    # 1. استقبال الفيديو
    async def receive_video(self, client, message):
        v_id = str(message.id)
        # جلب المدة إذا كان فيديو أو ملف
        duration_sec = 0
        if message.video:
            duration_sec = message.video.duration
        elif message.document and hasattr(message.document, "duration"):
            duration_sec = message.document.duration

        # حفظ الفيديو وتغيير الحالة لانتظار البوستر
        await self.db_execute(
            "INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
            (v_id, duration_sec, "waiting_poster"),
            fetch=False
        )
        await message.reply_text("✅ تم استلام الفيديو.\n🖼 الآن أرسل **البوستر** (صورة فقط):")

    # 2. استقبال البوستر
    async def receive_poster(self, client, message):
        # جلب آخر فيديو ينتظر بوستر بغض النظر عن المرسل
        res = await self.db_execute(
            "SELECT v_id FROM videos WHERE status='waiting_poster' ORDER BY rowid DESC LIMIT 1"
        )
        if not res: 
            return # لا يوجد فيديو ينتظر بوستر حالياً
        
        v_id = res[0][0]
        await self.db_execute(
            "UPDATE videos SET poster_id=?, status='awaiting_ep' WHERE v_id=?",
            (message.photo.file_id, v_id),
            fetch=False
        )
        await message.reply_text("🖼 تم حفظ البوستر.\n🔢 أرسل الآن **رقم الحلقة**:")

    # 3. استلام رقم الحلقة وعرض الجودات
    async def receive_ep_number(self, client, message):
        if not message.text or not message.text.isdigit(): 
            return
        
        # جلب آخر فيديو ينتظر رقم الحلقة
        res = await self.db_execute(
            "SELECT v_id FROM videos WHERE status='awaiting_ep' ORDER BY rowid DESC LIMIT 1"
        )
        if not res: 
            return
        
        v_id = res[0][0]
        ep_num = int(message.text)

        await self.db_execute(
            "UPDATE videos SET ep_num=?, status='waiting_quality' WHERE v_id=?",
            (ep_num, v_id),
            fetch=False
        )

        # عرض أزرار الجودة
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("SD", callback_data=f"p_SD_{v_id}"),
                InlineKeyboardButton("HD", callback_data=f"p_HD_{v_id}"),
                InlineKeyboardButton("4K", callback_data=f"p_4K_{v_id}")
            ]
        ])
        await message.reply_text(f"✅ تم تحديد الحلقة {ep_num}.\n✨ اختر الجودة المطلوبة للنشر:", reply_markup=markup)
