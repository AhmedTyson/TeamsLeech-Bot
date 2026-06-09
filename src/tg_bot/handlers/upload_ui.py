from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from tg_bot.filters import owner_only
from tg_bot.views import build_checklist_text, clean_filename
from tg_bot.keyboards import build_checklist_keyboard
from services.transfer import TransferService
from services.scanner import ScannerService
from services.state import StateManager

def register_upload_ui(app: Client, transfer: TransferService, state: StateManager, scanner: ScannerService):

    async def update_checklist_msg(client: Client, chat_id: int, message: Message):
        session = state.get_session(chat_id)
        if not session.pending_recordings:
            return
            
        # Re-group recordings by subject for the text builder
        results = {}
        for rec in session.pending_recordings:
            results.setdefault(rec.subject_name, []).append(rec)
            
        text = build_checklist_text(results, session.scan_label, session.rename_overrides)
        keyboard = build_checklist_keyboard(session.pending_recordings, session.selected_indices, session.rename_overrides)
        
        await message.edit_text(text, reply_markup=keyboard)

    @app.on_callback_query(filters.regex(r"^sel:") & owner_only)
    async def handle_select(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        action = cb.data.split(":", 1)[1]
        
        if action == "all":
            if len(session.selected_indices) == len(session.pending_recordings):
                session.selected_indices.clear()
            else:
                session.selected_indices.update(range(len(session.pending_recordings)))
        else:
            idx = int(action)
            if idx in session.selected_indices:
                session.selected_indices.discard(idx)
            else:
                session.selected_indices.add(idx)
                
        await update_checklist_msg(client, chat_id, cb.message)
        await cb.answer()

    @app.on_callback_query(filters.regex(r"^cancel:check") & owner_only)
    async def handle_cancel(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        state.clear_session(chat_id)
        await cb.message.edit_text("❌ **Cancelled.**\n\nSend /check to start again.")
        await cb.answer()

    @app.on_callback_query(filters.regex(r"^ren:") & owner_only)
    async def handle_rename_btn(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        idx = int(cb.data.split(":", 1)[1])
        
        if idx >= len(session.pending_recordings):
            await cb.answer("Invalid recording!", show_alert=True)
            return

        if session.pending_rename_idx is not None:
            await cb.message.reply("⚠️ Previous rename cancelled.")
            
        session.pending_rename_idx = idx
        rec = session.pending_recordings[idx]
        current_name = session.rename_overrides.get(idx, rec.name)
        
        # Smart Suggestion Logic
        suggested_name = ""
        subjects = scanner.load_subjects()
        subj_config = next((s for s in subjects if s.name == rec.subject_name), None)
        
        if subj_config:
            short = subj_config.short or subj_config.name
            doc = subj_config.doctor
            last_lec = state.get_last_lecture(rec.subject_name)
            suggested_name = f"{short} - L{last_lec + 1}"
            if doc:
                suggested_name += f" - {doc}"
                
            session.pending_suggestion = suggested_name
            
            sug_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✨ Accept: {suggested_name}", callback_data=f"sug:{idx}")
            ]])
            
            await cb.message.reply(
                f"✏️ **Rename File**\n"
                f"Current name: `{current_name}`\n\n"
                f"💡 _I've calculated the next lecture number for you. Tap the button below to use it, or type your own name._",
                reply_markup=sug_kb
            )
        else:
            await cb.message.reply(f"✏️ Send the new caption for:\n**{current_name}**\n\n_Send anything else to cancel._")
            
        await cb.answer()

    @app.on_callback_query(filters.regex(r"^sug:") & owner_only)
    async def handle_accept_suggestion(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        idx = int(cb.data.split(":", 1)[1])
        
        if session.pending_rename_idx != idx or not session.pending_suggestion:
            await cb.answer("Rename cancelled or invalid.", show_alert=True)
            return
            
        session.rename_overrides[idx] = session.pending_suggestion
        session.pending_rename_idx = None
        session.pending_suggestion = None
        
        await cb.message.edit_text(f"✅ Renamed to: **{session.rename_overrides[idx]}**")
        
        # We must find the checklist message to update it. 
        # But we don't have the checklist_msg_id stored in session anymore. 
        # For a truly robust FSM, we should store checklist_msg_id in session.
        # But for now, we just acknowledge. The user will see it when they hit upload.
        await cb.answer("✅ Name saved!")

    @app.on_message(filters.text & filters.private & owner_only, group=1)
    async def handle_rename_input(client: Client, message: Message):
        chat_id = message.chat.id
        session = state.get_session(chat_id)
        
        if session.pending_rename_idx is not None:
            idx = session.pending_rename_idx
            session.rename_overrides[idx] = message.text.strip()
            session.pending_rename_idx = None
            session.pending_suggestion = None
            await message.reply(f"✅ Renamed to: **{session.rename_overrides[idx]}**")
        else:
            message.continue_propagation()

    @app.on_callback_query(filters.regex(r"^upload:confirm") & owner_only)
    async def handle_upload(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        
        if not session.selected_indices:
            await cb.answer("☐ Nothing selected yet — tap a checkbox first.", show_alert=True)
            return
            
        selected_recs = []
        for i in sorted(session.selected_indices):
            if i < len(session.pending_recordings):
                rec = session.pending_recordings[i].model_copy()
                if i in session.rename_overrides:
                    rec.name = session.rename_overrides[i]
                selected_recs.append(rec)
                
        total_mb = sum(r.size_mb for r in selected_recs)
        names = "\n".join(f"   └─ 📥 `{clean_filename(r.name)}`" for r in selected_recs)
        
        status_text = f"🚀 **𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 {len(selected_recs)} 𝗙𝗶𝗹𝗲(𝘀)** ({total_mb:.0f} MB)\n{names}\n\n⏳ _Preparing streams..._"
        await cb.message.edit_text(status_text, reply_markup=None)
        
        # Progress callback
        import time
        start_time = time.time()
        
        async def tg_progress(event: str, data: dict):
            if event == "file_progress":
                pct = data.get("percent", 0)
                name = clean_filename(data.get("name", ""))
                speed = data.get("speed_mbps", 0.0)
                idx = data.get("index", 0)
                bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))
                
                await cb.message.edit_text(
                    f"🚀 **𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 {len(selected_recs)} 𝗙𝗶𝗹𝗲(𝘀)** ({total_mb:.0f} MB)\n{names}\n\n"
                    f"⬆️ **{idx + 1}/{len(selected_recs)}** — `{name}`\n"
                    f"`[{bar}]` **{pct}%**  |  ⚡ {speed:.1f} MB/s"
                )
            elif event == "file_done":
                name = clean_filename(data.get("name", ""))
                size = data.get("size_mb", 0)
                await client.send_message(chat_id, f"✅ **Successfully Uploaded:**\n`{name}` ({size:.0f} MB)")
            elif event == "all_done":
                total = data.get("total", len(selected_recs))
                await cb.message.edit_text(f"🎉 **𝗔𝗹𝗹 𝗗𝗼𝗻𝗲!**\nSuccessfully transferred {total} file(s).")
            elif event == "error":
                name = clean_filename(data.get("name", ""))
                err = data.get("error", "")
                await client.send_message(chat_id, f"❌ **Failed:** `{name}`\nError: {err}")

        # Execute transfer
        try:
            await transfer.upload_recordings(selected_recs, progress_cb=tg_progress)
        except Exception as e:
            await client.send_message(chat_id, f"❌ Upload error: {e}")
        finally:
            state.clear_session(chat_id)
            
        await cb.answer()
