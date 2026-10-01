import re
from datetime import UTC, datetime
from typing import Any

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from teamsleech.models.domain import Recording, UserSession
from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.services.transfer import ProgressCallback, TransferService
from teamsleech.tg_bot.callbacks import callback_text, parse_callback_index
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_edit_text
from teamsleech.tg_bot.keyboards import build_checklist_keyboard
from teamsleech.tg_bot.views import build_checklist_text


def _get_rename_suggestion(
    rec: Recording, state: StateManager, scanner: ScannerService
) -> str | None:
    subjects = scanner.load_subjects()
    subj_config = next((s for s in subjects if s.name == rec.subject_name), None)
    if not subj_config:
        return None
    short = subj_config.short or subj_config.name
    doc = subj_config.doctor
    last_lec = state.get_last_lecture(rec.subject_name)
    name = f"{short} - L{last_lec + 1}"
    if doc:
        name += f" - {doc}"
    return name


def collect_selected(session: UserSession) -> list[tuple[int, Recording]]:
    """Snapshot (session_index, recording) pairs in stable order."""
    pairs = []
    for i in sorted(session.selected_indices):
        if 0 <= i < len(session.pending_recordings):
            pairs.append((i, session.pending_recordings[i]))
    return pairs


def apply_rename_overrides(
    pairs: list[tuple[int, Recording]], rename_overrides: dict[int, str]
) -> list[Recording]:
    """Return copies with override names applied.

    Never mutates the session's recordings, so a retry or re-sort
    still sees the original names.
    """
    recs = []
    for idx, rec in pairs:
        override = (rename_overrides or {}).get(idx)
        if override:
            recs.append(rec.model_copy(update={"name": override}))
        else:
            recs.append(rec.model_copy())
    return recs


def parse_recording_date(rec: Recording) -> datetime | None:
    """Best-effort upload timestamp.

    Accepts time as `HH:MM`, `HH:MM:SS`, or missing. Returns None
    when even the date is unparseable — callers must then leave
    the stored cursor untouched instead of advancing it falsely.
    """
    time_part = (rec.time or "").strip()
    if re.fullmatch(r"\d{2}:\d{2}", time_part):
        time_part += ":00"
    elif not re.fullmatch(r"\d{2}:\d{2}:\d{2}", time_part):
        time_part = "00:00:00"
    try:
        dt = datetime.fromisoformat(f"{rec.created}T{time_part}+00:00")
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def build_upload_summary(results: list[dict[str, Any]]) -> str:
    success = sum(1 for r in results if r.get("success"))
    failed = sum(1 for r in results if not r.get("success"))
    return f"✅ **Upload complete!**\n   ✔ {success} succeeded\n   ✘ {failed} failed"


def make_transfer_progress_cb(progress_msg: Message, total: int) -> ProgressCallback:
    async def progress_cb(action: str, data: dict[str, Any]) -> None:
        if action == "file_done":
            done = data.get("index", 0) + 1
            name = data.get("name", "file")
            elapsed = data.get("elapsed_s", 0)
            await safe_edit_text(
                progress_msg,
                f"📊 Progress: {done} / {total} files\n✅ Uploaded: `{name}` ({elapsed:.1f}s)",
            )
        elif action == "error":
            name = data.get("name", "file")
            err = data.get("error", "unknown")
            base = getattr(progress_msg, "text", None) or ""
            await safe_edit_text(
                progress_msg,
                f"{base}\n❌ `{name}` failed: {err}",
            )

    return progress_cb


async def commit_upload_results(state: StateManager, results: list[dict[str, Any]]) -> None:
    """Batch per-subject cursor + lecture commit.

    Unparseable dates still count the lecture but leave the stored
    cursor untouched instead of advancing it falsely.
    """
    progress: dict[str, dict[str, Any]] = {}
    for res in results:
        if not res.get("success"):
            continue
        rec = res.get("rec")
        if not rec:
            continue
        rec_date = parse_recording_date(rec)
        slot = progress.setdefault(rec.subject_name, {"last_run": None, "lectures": 0})
        if rec_date is not None and (slot["last_run"] is None or rec_date > slot["last_run"]):
            slot["last_run"] = rec_date
        slot["lectures"] += 1

    for subject, slot in progress.items():
        await state.save_subject_state(subject, slot["last_run"], slot["lectures"])


def register_upload_ui(
    app: Client, transfer: TransferService, state: StateManager, scanner: ScannerService
) -> None:
    async def update_checklist_msg(client: Client, chat_id: int, message: Message) -> None:
        session = state.get_session(chat_id)
        if not session.pending_recordings:
            return

        text = build_checklist_text(
            session.grouped_recordings, session.scan_label, session.rename_overrides
        )
        keyboard = build_checklist_keyboard(
            session.pending_recordings,
            session.selected_indices,
            session.rename_overrides,
        )

        await safe_edit_text(message, text, reply_markup=keyboard)

    @app.on_callback_query(filters.regex(r"^sel:pdfs$") & owner_only)
    async def handle_select_pdfs(client: Client, cb: CallbackQuery) -> None:
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        session.selected_indices = {
            i for i, r in enumerate(session.pending_recordings) if not r.is_video
        }
        await update_checklist_msg(client, chat_id, cb.message)
        await cb.answer(f"📄 Selected {len(session.selected_indices)} file(s)")

    @app.on_callback_query(filters.regex(r"^sel:videos$") & owner_only)
    async def handle_select_videos(client: Client, cb: CallbackQuery) -> None:
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        session.selected_indices = {
            i for i, r in enumerate(session.pending_recordings) if r.is_video
        }
        await update_checklist_msg(client, chat_id, cb.message)
        await cb.answer(f"🎬 Selected {len(session.selected_indices)} recording(s)")

    @app.on_callback_query(filters.regex(r"^sel:(all|\d+)$") & owner_only)
    async def handle_select(client: Client, cb: CallbackQuery) -> None:
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        data = callback_text(cb.data)
        if data is None or ":" not in data:
            await cb.answer("Invalid request.", show_alert=True)
            return
        action = data.split(":", 1)[1]

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
    async def handle_cancel(client: Client, cb: CallbackQuery) -> None:
        chat_id = cb.message.chat.id
        state.clear_session(chat_id)
        await safe_edit_text(
            cb.message,
            "❌ **Cancelled.**\n\nSend /check to start again.",
        )
        await cb.answer()

    @app.on_callback_query(filters.regex(r"^ren:\d+$") & owner_only)
    async def handle_rename_btn(client: Client, cb: CallbackQuery) -> None:
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        idx = parse_callback_index(cb.data)

        if idx is None or idx >= len(session.pending_recordings):
            await cb.answer("Invalid recording!", show_alert=True)
            return

        if session.pending_rename_idx is not None:
            await cb.message.reply("⚠️ Previous rename cancelled.")

        session.pending_rename_idx = idx
        # Rename owns text input now; drop a stale date wizard so the
        # typed name is not swallowed as a date.
        session.date_input_pending = False
        session.subject_filter = None
        rec = session.pending_recordings[idx]
        current_name = session.rename_overrides.get(idx, rec.name)

        suggested_name = _get_rename_suggestion(rec, state, scanner)
        if suggested_name:
            session.pending_suggestion = suggested_name

            sug_kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"✨ Accept: {suggested_name}",
                            callback_data=f"sug:{idx}",
                        )
                    ]
                ]
            )

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

    @app.on_callback_query(filters.regex(r"^sug:\d+$") & owner_only)
    async def handle_accept_suggestion(client: Client, cb: CallbackQuery) -> None:
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        idx = parse_callback_index(cb.data)

        if idx is None or (session.pending_rename_idx != idx or not session.pending_suggestion):
            await cb.answer("Rename cancelled or invalid.", show_alert=True)
            return

        session.rename_overrides[idx] = session.pending_suggestion
        session.pending_rename_idx = None
        session.pending_suggestion = None

        await safe_edit_text(
            cb.message,
            f"✅ Renamed to: **{session.rename_overrides[idx]}**",
        )
        await cb.answer("✅ Name saved!")

    @app.on_message(filters.text & filters.private & owner_only, group=1)
    async def handle_rename_input(client: Client, message: Message) -> None:
        chat_id = message.chat.id
        session = state.get_session(chat_id)

        if session.pending_rename_idx is not None:
            idx = session.pending_rename_idx
            if idx < 0 or idx >= len(session.pending_recordings):
                session.pending_rename_idx = None
                session.pending_suggestion = None
                await message.reply(
                    "❌ That recording is gone — the list changed. Tap rename again."
                )
                return
            session.rename_overrides[idx] = message.text.strip()
            session.pending_rename_idx = None
            session.pending_suggestion = None
            await message.reply(f"✅ Renamed to: **{session.rename_overrides[idx]}**")
        else:
            message.continue_propagation()  # type: ignore[no-untyped-call]

    @app.on_callback_query(filters.regex(r"^upload:confirm") & owner_only)
    async def handle_upload(client: Client, cb: CallbackQuery) -> None:
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        pairs = collect_selected(session)

        if not pairs:
            await cb.answer(
                "☐ Nothing selected yet — tap a checkbox first.",
                show_alert=True,
            )
            return

        await cb.answer("Starting upload...")
        selected_recs = apply_rename_overrides(pairs, session.rename_overrides)

        await safe_edit_text(
            cb.message,
            f"☁️ **Uploading {len(selected_recs)} file(s)...**\n"
            "_Please wait — this may take a while._",
        )

        progress_msg = await cb.message.reply(f"📊 Progress: 0 / {len(selected_recs)} files")
        progress_cb = make_transfer_progress_cb(progress_msg, len(selected_recs))

        try:
            results = await transfer.upload_recordings(selected_recs, progress_cb)
            await commit_upload_results(state, results)
            await safe_edit_text(progress_msg, build_upload_summary(results))
        except Exception as e:
            await safe_edit_text(progress_msg, f"❌ Upload failed: {e}")

        state.clear_session(chat_id)
