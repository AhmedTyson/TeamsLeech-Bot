"""
Phase 3 — bot

Telegram bot interface for TeamsLeech using Pyrogram.
Handles /check (subject buttons), text commands, /reauth recovery,
and multi-select recording checkboxes.

This module does NOT call fetcher.py or uploader.py directly.
It exposes handler functions that the orchestrator (main.py, Phase 5)
will wire up with the actual fetcher and uploader.

Public API
----------
create_bot()       → pyrogram.Client  (configured, not started)
register_handlers(app, on_fetch, on_upload) → None
"""

import os
import json
import logging
from typing import Callable, Any

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

log = logging.getLogger("bot")

# ───────────────────────── config ─────────────────────────────

def _load_subjects(path: str = "subjects_config.json") -> list[dict]:
    """Load subjects from JSON config (shared with fetcher)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("subjects", [])

# ───────────────────────── bot factory ────────────────────────

def create_bot(
    session_string: str | None = None,
    api_id: int | None = None,
    api_hash: str | None = None,
    bot_token: str | None = None,
) -> Client:
    """Create a Pyrogram Client configured from env vars or arguments.

    Environment variables (fallbacks):
        TELEGRAM_SESSION   – Pyrogram session string
        TELEGRAM_API_ID    – from my.telegram.org
        TELEGRAM_API_HASH  – from my.telegram.org
        TELEGRAM_BOT_TOKEN – from @BotFather
    """
    session = session_string or os.environ.get("TELEGRAM_SESSION", "")
    aid = api_id or int(os.environ.get("TELEGRAM_API_ID", "0"))
    ahash = api_hash or os.environ.get("TELEGRAM_API_HASH", "")
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")

    if not all([session, aid, ahash, token]):
        missing = []
        if not session: missing.append("TELEGRAM_SESSION")
        if not aid: missing.append("TELEGRAM_API_ID")
        if not ahash: missing.append("TELEGRAM_API_HASH")
        if not token: missing.append("TELEGRAM_BOT_TOKEN")
        raise RuntimeError(f"Missing Telegram env vars: {', '.join(missing)}")

    app = Client(
        name="teamsleech_bot",
        api_id=aid,
        api_hash=ahash,
        bot_token=token,
        session_string=session,
        in_memory=True,
    )
    log.info("Pyrogram bot client created.")
    return app

# ───────────────────────── UI builders ────────────────────────

def _build_subject_keyboard(subjects: list[dict]) -> InlineKeyboardMarkup:
    """Build the /check subject selection keyboard.

    Layout (from PRD §7):
        [ Advanced DB ]  [ Auditing ]  [ Econ of Info ]
        [ Internet Apps ]  [ MIS ]  [ O.R. ]
        [ ✅ Check All ]
    """
    buttons = []
    row: list[InlineKeyboardButton] = []

    for i, subj in enumerate(subjects):
        row.append(InlineKeyboardButton(
            text=subj["short"],
            callback_data=f"subj:{subj['name']}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Check All button on its own row
    buttons.append([InlineKeyboardButton(
        text="✅ Check All",
        callback_data="subj:__ALL__",
    )])

    return InlineKeyboardMarkup(buttons)


def _build_recording_checklist(
    results: dict[str, list[dict]],
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build the recording selection message and checkbox keyboard.

    Returns (message_text, keyboard_or_None).
    """
    total = sum(len(recs) for recs in results.values())

    if total == 0:
        # No recordings found
        subjects_checked = ", ".join(results.keys())
        return f"No new recordings found for {subjects_checked} ✅", None

    lines: list[str] = []
    buttons: list[list[InlineKeyboardButton]] = []
    idx = 0

    for subj_name, recs in results.items():
        if not recs:
            lines.append(f"\n📚 **{subj_name}** — No new recordings ✅")
            continue

        lines.append(f"\n📚 **{subj_name}** — {len(recs)} recording(s):")
        for rec in recs:
            lines.append(
                f"  🎥 `{rec['name']}` — {rec['size_mb']}MB — {rec['created']}"
            )
            # Each recording gets a checkbox button
            buttons.append([InlineKeyboardButton(
                text=f"☐ {rec['name'][:40]}",
                callback_data=f"sel:{idx}",
            )])
            idx += 1

    # Upload Selected button
    buttons.append([InlineKeyboardButton(
        text="📤 Upload Selected",
        callback_data="upload:confirm",
    )])

    text = "**New recordings found:**\n" + "\n".join(lines)
    return text, InlineKeyboardMarkup(buttons)


REAUTH_MESSAGE = """⚠️ **Session Expired**

Your Microsoft refresh token has expired. Follow these steps to recover:

**Step 1:** Open Teams in your browser → Press F12 → Network tab → log in

**Step 2:** Find the `login.microsoftonline.com` POST request → copy `refresh_token` from the request body

**Step 3:** Go to your GitHub repo → Settings → Secrets → Update `TEAMS_REFRESH_TOKEN` with the new token

**Step 4:** Come back here and send `/check` to verify it works

_This takes less than 5 minutes._"""

# ───────────────────────── handler registration ───────────────

# In-memory state for recording selections per user
_pending_results: dict[int, dict[str, list[dict]]] = {}  # chat_id → results
_pending_selections: dict[int, set[int]] = {}             # chat_id → selected indices
_flat_recordings: dict[int, list[dict]] = {}              # chat_id → flat list


def register_handlers(
    app: Client,
    on_fetch: Callable[[str | None], dict[str, list[dict]]],
    on_upload: Callable[[list[dict]], Any],
    owner_chat_id: int | None = None,
) -> None:
    """Register all Telegram command and callback handlers.

    Parameters
    ----------
    app : Client
        The Pyrogram client to register handlers on.
    on_fetch : callable(subject_filter: str | None) → dict
        Called to fetch recordings. Returns {subject: [recording_dicts]}.
        Provided by the orchestrator (main.py) — wraps fetcher.fetch_recordings.
    on_upload : callable(recordings: list[dict]) → Any
        Called to upload selected recordings. Provided by orchestrator.
        Receives list of recording dicts (drive_id, item_id, etc.).
    owner_chat_id : int | None
        If set, only respond to this specific chat ID.
    """
    owner_id = owner_chat_id or int(os.environ.get("TELEGRAM_CHAT_ID", "0"))

    def _is_owner(msg_or_cb) -> bool:
        """Only respond to the bot owner."""
        if not owner_id:
            return True
        chat_id = (
            msg_or_cb.chat.id if hasattr(msg_or_cb, "chat")
            else msg_or_cb.message.chat.id
        )
        return chat_id == owner_id

    # ── /check command ───────────────────────────────────────────
    @app.on_message(filters.command("check") & filters.private)
    async def handle_check(client: Client, message: Message) -> None:
        if not _is_owner(message):
            return

        subjects = _load_subjects()
        keyboard = _build_subject_keyboard(subjects)
        await message.reply(
            "**What do you want to check?**",
            reply_markup=keyboard,
        )
        log.info("/check command received — subject keyboard sent.")

    # ── /reauth command ──────────────────────────────────────────
    @app.on_message(filters.command("reauth") & filters.private)
    async def handle_reauth(client: Client, message: Message) -> None:
        if not _is_owner(message):
            return

        await message.reply(REAUTH_MESSAGE)
        log.info("/reauth command received — recovery guide sent.")

    # ── /start command ───────────────────────────────────────────
    @app.on_message(filters.command("start") & filters.private)
    async def handle_start(client: Client, message: Message) -> None:
        if not _is_owner(message):
            return

        await message.reply(
            "📡 **TeamsLeech Bot**\n\n"
            "Send /check to scan for new lecture recordings.\n"
            "Send /reauth if your session has expired."
        )

    # ── Text message — match subject name ────────────────────────
    @app.on_message(filters.text & filters.private & ~filters.command(["check", "reauth", "start"]))
    async def handle_text(client: Client, message: Message) -> None:
        if not _is_owner(message):
            return

        text = message.text.strip()
        subjects = _load_subjects()

        # Try to match text to a subject name or short name
        matched_subject = None
        text_lower = text.lower()
        for subj in subjects:
            if (text_lower == subj["name"].lower()
                    or text_lower == subj.get("short", "").lower()):
                matched_subject = subj["name"]
                break
            # Also match any keyword
            for kw in subj.get("keywords", []):
                if text_lower == kw.lower():
                    matched_subject = subj["name"]
                    break
            if matched_subject:
                break

        if not matched_subject:
            return  # Not a subject — ignore silently

        await message.reply(f"🔍 Scanning **{matched_subject}**...")

        try:
            results = on_fetch(matched_subject)
        except Exception as e:
            await message.reply(f"❌ Fetch error: {e}")
            log.error("Fetch failed for '%s': %s", matched_subject, e)
            return

        chat_id = message.chat.id
        text_reply, keyboard = _build_recording_checklist(results)
        _store_results(chat_id, results)
        await message.reply(text_reply, reply_markup=keyboard)

    # ── Subject button callback ──────────────────────────────────
    @app.on_callback_query(filters.regex(r"^subj:"))
    async def handle_subject_select(client: Client, cb: CallbackQuery) -> None:
        if not _is_owner(cb):
            return

        subject_key = cb.data.split(":", 1)[1]
        subject_filter = None if subject_key == "__ALL__" else subject_key

        label = "all subjects" if subject_filter is None else subject_filter
        await cb.message.edit_text(f"🔍 Scanning **{label}**...")

        try:
            results = on_fetch(subject_filter)
        except Exception as e:
            await cb.message.edit_text(f"❌ Fetch error: {e}")
            log.error("Fetch failed: %s", e)
            return

        chat_id = cb.message.chat.id
        text, keyboard = _build_recording_checklist(results)
        _store_results(chat_id, results)
        await cb.message.edit_text(text, reply_markup=keyboard)
        await cb.answer()

    # ── Checkbox toggle callback ─────────────────────────────────
    @app.on_callback_query(filters.regex(r"^sel:"))
    async def handle_select_toggle(client: Client, cb: CallbackQuery) -> None:
        if not _is_owner(cb):
            return

        chat_id = cb.message.chat.id
        idx = int(cb.data.split(":", 1)[1])

        if chat_id not in _pending_selections:
            _pending_selections[chat_id] = set()

        selections = _pending_selections[chat_id]
        if idx in selections:
            selections.discard(idx)
        else:
            selections.add(idx)

        # Rebuild keyboard with updated check/uncheck marks
        flat = _flat_recordings.get(chat_id, [])
        buttons: list[list[InlineKeyboardButton]] = []
        for i, rec in enumerate(flat):
            mark = "☑" if i in selections else "☐"
            buttons.append([InlineKeyboardButton(
                text=f"{mark} {rec['name'][:40]}",
                callback_data=f"sel:{i}",
            )])
        buttons.append([InlineKeyboardButton(
            text=f"📤 Upload Selected ({len(selections)})",
            callback_data="upload:confirm",
        )])

        await cb.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        await cb.answer()

    # ── Upload confirm callback ──────────────────────────────────
    @app.on_callback_query(filters.regex(r"^upload:confirm"))
    async def handle_upload_confirm(client: Client, cb: CallbackQuery) -> None:
        if not _is_owner(cb):
            return

        chat_id = cb.message.chat.id
        selections = _pending_selections.get(chat_id, set())
        flat = _flat_recordings.get(chat_id, [])

        if not selections:
            await cb.answer("No recordings selected!", show_alert=True)
            return

        selected_recs = [flat[i] for i in sorted(selections) if i < len(flat)]

        if not selected_recs:
            await cb.answer("Selection invalid — try /check again.", show_alert=True)
            return

        # Confirm selection
        names = "\n".join(f"  📥 {r['name']}" for r in selected_recs)
        await cb.message.edit_text(
            f"**Uploading {len(selected_recs)} recording(s):**\n{names}\n\n"
            "Starting upload..."
        )

        try:
            on_upload(selected_recs)
        except Exception as e:
            await cb.message.reply(f"❌ Upload error: {e}")
            log.error("Upload failed: %s", e)
            return

        # Clean up state
        _pending_results.pop(chat_id, None)
        _pending_selections.pop(chat_id, None)
        _flat_recordings.pop(chat_id, None)
        await cb.answer()


def _store_results(chat_id: int, results: dict[str, list[dict]]) -> None:
    """Store fetch results and build flat recording list for selection."""
    _pending_results[chat_id] = results
    _pending_selections[chat_id] = set()

    flat: list[dict] = []
    for recs in results.values():
        flat.extend(recs)
    _flat_recordings[chat_id] = flat
