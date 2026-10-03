from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from teamsleech.models.domain import Recording
from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.services.transfer import TransferService
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_edit_text
from teamsleech.tg_bot.keyboards import build_checklist_keyboard
from teamsleech.tg_bot.views import build_checklist_text


def _get_rename_suggestion(
    rec: Recording, state: StateManager, scanner: ScannerService
) -> str | None:
    subjects = scanner.load_subjects()
    subj_config = next(
        (s for s in subjects if s.name == rec.subject_name), None
    )
    if not subj_config:
        return None
    short = subj_config.short or subj_config.name
    doc = subj_config.doctor
    last_lec = state.get_last_lecture(rec.subject_name)
    name = f"{short} - L{last_lec + 1}"
    if doc:
        name += f" - {doc}"
    return name

def register_upload_ui(
    app: Client, transfer: TransferService, state: StateManager, scanner: ScannerService
):
    async def update_checklist_msg(
        client: Client, chat_id: int, message: Message
    ):
        session = state.get_session(chat_id)
        if not session.pending_recordings:
            return

        doctors = {s.name: s.doctor for s in scanner.load_subjects()}
        text = build_checklist_text(
            session.grouped_recordings, session.scan_label, session.rename_overrides,
            doctors=doctors,
        )
        keyboard = build_checklist_keyboard(
            session.pending_recordings,
            session.selected_indices,
            session.rename_overrides,
        )

        await safe_edit_text(message, text, reply_markup=keyboard)

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
        await safe_edit_text(
            cb.message,
            "❌ **Cancelled.**\n\nSend /check to start again.",
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

        suggested_name = _get_rename_suggestion(rec, state, scanner)
        if suggested_name:
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

        await safe_edit_text(
            cb.message,
            f"✅ Renamed to: **{session.rename_overrides[idx]}**",
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

        await cb.answer("Starting upload...")

        selected_recs = []
        for i in sorted(session.selected_indices):
            if i < len(session.pending_recordings):
                rec = session.pending_recordings[i]
                selected_recs.append(rec)

                override_name = session.rename_overrides.get(i)
                if override_name:
                    rec.name = override_name

        await safe_edit_text(
            cb.message,
            f"☁️ **Uploading {len(selected_recs)} file(s)...**\n"
            "_Please wait — this may take a while._",
        )

        progress_msg = await cb.message.reply(
            f"📊 Progress: 0 / {len(selected_recs)} files"
        )
        rows: dict[int, str] = {}
        done_count = 0

        def _short(name: str) -> str:
            return name if len(name) <= 30 else name[:27] + "…"

        async def _render():
            lines = [
                f"📊 **Uploading {done_count}/{len(selected_recs)}…**"
            ]
            for i in range(len(selected_recs)):
                lines.append(f"{i + 1}. {rows.get(i, '⏳ waiting')}")
            await safe_edit_text(progress_msg, "\n".join(lines))

        async def progress_cb(action: str, data: dict):
            nonlocal done_count
            idx = data.get("index", 0)
            name = _short(data.get("name", "file"))
            if action == "start":
                rows.clear()
                done_count = 0
                await _render()
            elif action == "dl_start":
                rows[idx] = f"⬇️ starting… {name}"
                await _render()
            elif action == "dl_progress":
                if data.get("done"):
                    rows[idx] = f"⬇️ done ({data.get('written_mb', 0):.0f} MB) {name}"
                elif data.get("percent") is not None:
                    rows[idx] = (
                        f"⬇️ {data['percent']}%"
                        f" · {data.get('speed_mbps', 0):.1f} MB/s {name}"
                    )
                else:
                    rows[idx] = f"⬇️ {data.get('written_mb', 0):.0f} MB {name}"
                await _render()
            elif action == "dl_done":
                rows[idx] = f"⬇️ done ({data.get('size_mb', 0):.0f} MB) {name}"
                await _render()
            elif action == "file_progress":
                rows[idx] = f"⬆️ {data.get('percent', 0)}% {name}"
                await _render()
            elif action == "file_done":
                done_count += 1
                elapsed = data.get("elapsed_s", 0)
                rows[idx] = f"✅ done in {elapsed:.0f}s {name}"
                await _render()
            elif action == "error":
                err = data.get("error", "unknown")
                rows[idx] = f"❌ {name}"
                await _render()
                await cb.message.reply(
                    f"❌ `{data.get('name', 'file')}` failed:\n{err}",
                )

        try:
            results = await transfer.upload_recordings(
                selected_recs, progress_cb
            )
            success = sum(1 for r in results if r.get("success"))
            failed = sum(1 for r in results if not r.get("success"))

            for res in results:
                if not res.get("success"):
                    continue
                rec = res.get("rec")
                if not rec:
                    continue

                rec_time_str = f"{rec.created}T{rec.time or '00:00'}:00+00:00"
                try:
                    rec_date = datetime.fromisoformat(rec_time_str)
                    if rec_date > state.get_last_run(rec.subject_name):
                        await state.save_last_run(rec.subject_name, rec_date)
                        await state.save_last_lecture(
                            rec.subject_name,
                            state.get_last_lecture(rec.subject_name) + 1,
                        )
                except ValueError:
                    await state.save_last_run(rec.subject_name)
                    await state.save_last_lecture(
                        rec.subject_name,
                        state.get_last_lecture(rec.subject_name) + 1,
                    )

            summary = (
                f"✅ **Upload complete!**\n"
                f"   ✔ {success} succeeded\n"
                f"   ✘ {failed} failed"
            )
            await safe_edit_text(progress_msg, summary)
        except Exception as e:
            await safe_edit_text(progress_msg, f"❌ Upload failed: {e}")

        state.clear_session(chat_id)
