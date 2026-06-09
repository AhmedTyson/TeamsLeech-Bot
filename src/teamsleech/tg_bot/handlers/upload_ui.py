from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.services.transfer import TransferService
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.keyboards import build_checklist_keyboard
from teamsleech.tg_bot.views import build_checklist_text

def register_upload_ui(
    app: Client, transfer: TransferService, state: StateManager, scanner: ScannerService
):
    async def update_checklist_msg(
        client: Client, chat_id: int, message: Message
    ):
        session = state.get_session(chat_id)
        if not session.pending_recordings:
            return

        results = {}
        for rec in session.pending_recordings:
            results.setdefault(rec.subject_name, []).append(rec)

        text = build_checklist_text(
            results, session.scan_label, session.rename_overrides
        )
        keyboard = build_checklist_keyboard(
            session.pending_recordings,
            session.selected_indices,
            session.rename_overrides,
        )

        await message.edit_text(text, reply_markup=keyboard)

    @app.on_callback_query(filters.regex(r"^sel:pdfs$") & owner_only)
    async def handle_select_pdfs(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        session.selected_indices = {
            i for i, r in enumerate(session.pending_recordings)
            if not r.is_video
        }
        await update_checklist_msg(client, chat_id, cb.message)
        await cb.answer(f"📄 Selected {len(session.selected_indices)} file(s)")

    @app.on_callback_query(filters.regex(r"^sel:videos$") & owner_only)
    async def handle_select_videos(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        session.selected_indices = {
            i for i, r in enumerate(session.pending_recordings)
            if r.is_video
        }
        await update_checklist_msg(client, chat_id, cb.message)
        await cb.answer(f"🎬 Selected {len(session.selected_indices)} recording(s)")

    @app.on_callback_query(filters.regex(r"^sel:(all|\d+)$") & owner_only)
    async def handle_select(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        action = cb.data.split(":", 1)[1]

        if action == "all":
            if len(session.selected_indices) == len(session.pending_recordings):
                session.selected_indices.clear()
            else:
                session.selected_indices.update(
                    range(len(session.pending_recordings))
                )
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
        await cb.message.edit_text(
            "❌ **Cancelled.**\n\nSend /check to start again."
        )
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

        subjects = scanner.load_subjects()
        subj_config = next(
            (s for s in subjects if s.name == rec.subject_name), None
        )

        if subj_config:
            short = subj_config.short or subj_config.name
            doc = subj_config.doctor
            last_lec = state.get_last_lecture(rec.subject_name)
            suggested_name = f"{short} - L{last_lec + 1}"
            if doc:
                suggested_name += f" - {doc}"

            session.pending_suggestion = suggested_name

            sug_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        f"✨ Accept: {suggested_name}",
                        callback_data=f"sug:{idx}",
                    )
                ]
            ])

            await cb.message.reply(
                f"✏️ **Rename File**\n"
                f"Current name: `{current_name}`\n\n"
                f"💡 _I've calculated the next lecture number for you."
                " Tap the button below to use it, or type your own name._",
                reply_markup=sug_kb,
            )
        else:
            await cb.message.reply(
                f"✏️ Send the new caption for:\n"
                f"**{current_name}**\n\n"
                "_Send anything else to cancel._"
            )

        await cb.answer()

    @app.on_callback_query(filters.regex(r"^sug:") & owner_only)
    async def handle_accept_suggestion(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        idx = int(cb.data.split(":", 1)[1])

        if (
            session.pending_rename_idx != idx
            or not session.pending_suggestion
        ):
            await cb.answer(
                "Rename cancelled or invalid.", show_alert=True
            )
            return

        session.rename_overrides[idx] = session.pending_suggestion
        session.pending_rename_idx = None
        session.pending_suggestion = None

        await cb.message.edit_text(
            f"✅ Renamed to: **{session.rename_overrides[idx]}**"
        )
        await cb.answer("✅ Name saved!")

    @app.on_message(
        filters.text & filters.private & owner_only, group=1
    )
    async def handle_rename_input(client: Client, message: Message):
        chat_id = message.chat.id
        session = state.get_session(chat_id)

        if session.pending_rename_idx is not None:
            idx = session.pending_rename_idx
            session.rename_overrides[idx] = message.text.strip()
            session.pending_rename_idx = None
            session.pending_suggestion = None
            await message.reply(
                f"✅ Renamed to: **{session.rename_overrides[idx]}**"
            )
        else:
            message.continue_propagation()

    @app.on_callback_query(filters.regex(r"^upload:confirm") & owner_only)
    async def handle_upload(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)

        if not session.selected_indices:
            await cb.answer(
                "☐ Nothing selected yet — tap a checkbox first.",
                show_alert=True,
            )
            return

        selected_recs = []
        for i in sorted(session.selected_indices):
            if i < len(session.pending_recordings):
                rec = session.pending_recordings[i]
                selected_recs.append(rec)

                override_name = session.rename_overrides.get(i)
                if override_name:
                    rec.name = override_name

        await cb.message.edit_text(
            f"☁️ **Uploading {len(selected_recs)} file(s)...**\n"
            "_Please wait — this may take a while._"
        )

        progress_msg = await cb.message.reply(
            f"📊 Progress: 0 / {len(selected_recs)} files"
        )

        async def progress_cb(action: str, data: dict):
            if action == "file_done":
                done = data.get("index", 0) + 1
                name = data.get("name", "file")
                elapsed = data.get("elapsed_s", 0)
                await progress_msg.edit_text(
                    f"📊 Progress: {done} / {len(selected_recs)} files\n"
                    f"✅ Uploaded: `{name}` ({elapsed:.1f}s)"
                )
            elif action == "error":
                name = data.get("name", "file")
                err = data.get("error", "unknown")
                await progress_msg.edit_text(
                    f"{progress_msg.text}\n❌ `{name}` failed: {err}"
                )

        try:
            results = await transfer.upload_recordings(
                selected_recs, progress_cb
            )
            success = sum(1 for r in results if r.get("success"))
            failed = sum(1 for r in results if not r.get("success"))

            summary = (
                f"✅ **Upload complete!**\n"
                f"   ✔ {success} succeeded\n"
                f"   ✘ {failed} failed"
            )
            await progress_msg.edit_text(summary)
        except Exception as e:
            await progress_msg.edit_text(f"❌ Upload failed: {e}")

        state.clear_session(chat_id)
        await cb.answer()
