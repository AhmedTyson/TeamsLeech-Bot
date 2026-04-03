"""
Phase 3 — bot (v2 — UI overhaul)

Telegram bot interface for TeamsLeech using Pyrogram.
Handles /check (subject buttons), date selection (single day, range,
this week, today), text commands, /reauth recovery, multi-select
recording checkboxes, rename, select all, change date, and cancel.

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
import re
import asyncio
from datetime import datetime, date as date_type, timedelta, timezone
from typing import Callable, Any

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# Persistent reply keyboard shown at the bottom of every message
REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔍 Check Recordings"), KeyboardButton("🔑 Reauth")],
    ],
    resize_keyboard=True,
)

log = logging.getLogger("bot")

# ───────────────────────── constants ──────────────────────────────

DIVIDER_THIN = "───────────────────"
DIVIDER_THICK = "━━━━━━━━━━━━━━━━━━"

# Emoji number labels: 1️⃣ through 🔟, then fallback to plain digits
_NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

MAX_DATE_RANGE_DAYS = 30


def _num_label(n: int) -> str:
    """Return emoji number for 1-based index n."""
    if 1 <= n <= 10:
        return _NUM_EMOJI[n - 1]
    return f"**{n}.**"


def _clean_filename(name: str) -> str:
    """Remove redundant '-Meeting Recording' suffix from filename."""
    return re.sub(r"-Meeting Recording", "", name)


def _format_date_short(date_str: str) -> str:
    """Format 'YYYY-MM-DD' → 'Apr 03'."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.strftime("%b %d")
    except ValueError:
        return date_str


def _get_current_week_range() -> tuple[str, str]:
    """Return (monday_str, sunday_str) for the current week."""
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def _validate_date_range(start: str, end: str) -> tuple[bool, str]:
    """Validate a date range. Returns (is_valid, error_message)."""
    try:
        s = date_type.fromisoformat(start)
        e = date_type.fromisoformat(end)
    except ValueError:
        return False, "❌ Invalid date format. Use `YYYY-MM-DD`."
    if s > e:
        return False, "❌ Start date must be before or equal to end date."
    if (e - s).days > MAX_DATE_RANGE_DAYS:
        return False, f"❌ Date range cannot exceed {MAX_DATE_RANGE_DAYS} days."
    return True, ""


# ───────────────────────── config ─────────────────────────────────

def _load_subjects(path: str = "subjects_config.json") -> list[dict]:
    """Load subjects from JSON config (shared with fetcher)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("subjects", [])

# ───────────────────────── bot factory ────────────────────────────

def create_bot(
    api_id: int | None = None,
    api_hash: str | None = None,
    bot_token: str | None = None,
) -> Client:
    """Create a Pyrogram Client configured from env vars or arguments."""
    aid = api_id or int(os.environ.get("TELEGRAM_API_ID", "0"))
    ahash = api_hash or os.environ.get("TELEGRAM_API_HASH", "")
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")

    if not all([aid, ahash, token]):
        missing = []
        if not aid: missing.append("TELEGRAM_API_ID")
        if not ahash: missing.append("TELEGRAM_API_HASH")
        if not token: missing.append("TELEGRAM_BOT_TOKEN")
        raise RuntimeError(f"Missing Telegram env vars: {', '.join(missing)}")

    app = Client(
        name="teamsleech_bot",
        api_id=aid,
        api_hash=ahash,
        bot_token=token,
        in_memory=True,
    )
    log.info("Pyrogram bot client created.")
    return app

# ───────────────────────── UI builders ────────────────────────────

def _build_subject_keyboard(subjects: list[dict]) -> InlineKeyboardMarkup:
    """Build the /check subject selection keyboard.

    Layout:
        [ Advanced DB ]  [ Auditing ]  [ Econ of Info ]
        [ Internet Apps ]  [ MIS ]  [ O.R. ]
        [ Sections 👥 ]  [ جهاد مجدي 👩‍🏫 ]  [ رانيا شحاتة 👩‍🏫 ]
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


def _build_checklist_text(
    results: dict[str, list[dict]],
    scan_label: str = "",
    rename_overrides: dict[int, str] | None = None,
) -> str:
    """Build the checklist message text with improved formatting.

    Progressive compaction if text exceeds Telegram's 4096-char limit.
    """
    total = sum(len(recs) for recs in results.values())

    if total == 0:
        subjects_checked = ", ".join(results.keys())
        header = f"📡 **Scan Results**"
        if scan_label:
            header += f"\n📅 {scan_label}"
        return f"{header}\n{DIVIDER_THICK}\n\n✅ No new recordings found\n_{subjects_checked}_"

    overrides = rename_overrides or {}
    is_multi = len(results) > 1

    for level in range(4):
        lines: list[str] = []

        # Header
        if level <= 1:
            lines.append("📡 **Scan Results**")
            if scan_label:
                lines.append(f"📅 {scan_label}")
            lines.append(DIVIDER_THICK)
        else:
            lines.append(f"📡 **{total} recording(s) found**")

        idx = 0
        for subj_name, recs in results.items():
            if not recs:
                if level <= 1:
                    lines.append(f"\n📚 **{subj_name}** — ✅ No new recordings")
                continue

            # Subject header
            if is_multi:
                if level <= 1:
                    lines.append(f"\n📚 **{subj_name}** — {len(recs)} recording(s)")
                elif level == 2:
                    lines.append(f"\n📚 **{subj_name}**")
                elif level == 3:
                    lines.append(f"📚 **{subj_name}** — {len(recs)} file(s)")

            for rec in recs:
                if level == 3:
                    idx += 1
                    continue

                display_name = _clean_filename(overrides.get(idx, rec["name"]))
                num = _num_label(idx + 1)
                date_short = _format_date_short(rec["created"])

                if level == 0:
                    lines.append(
                        f"\n{num}  📅 {date_short}  •  💾 {rec['size_mb']} MB\n"
                        f"    📄 {display_name}"
                    )
                elif level == 1:
                    lines.append(
                        f"{num} 📅 {date_short} • 💾 {rec['size_mb']} MB\n"
                        f"📄 {display_name}"
                    )
                elif level == 2:
                    short_name = display_name[:55] + "..." if len(display_name) > 58 else display_name
                    lines.append(f"{num} {short_name}")

                idx += 1

            # Separator between subjects
            if is_multi and level <= 1:
                lines.append(DIVIDER_THIN)

        # Footer
        if level <= 1:
            lines.append(f"\n📊 **{total}** recording(s) found")
        if level == 3:
            lines.append("\n_Use the buttons below to select & upload._")

        full_text = "\n".join(lines)
        if len(full_text) <= 4000:
            return full_text

    return "\n".join(lines[:100]) + "\n\n_...list truncated due to Telegram limits._"


def _build_checklist_keyboard(
    flat: list[dict],
    selections: set[int],
    rename_overrides: dict[int, str] | None = None,
) -> InlineKeyboardMarkup:
    """Build the checkbox + rename + upload + select-all + change-date keyboard."""
    overrides = rename_overrides or {}
    buttons: list[list[InlineKeyboardButton]] = []

    for i, rec in enumerate(flat):
        mark = "☑" if i in selections else "☐"
        num = _num_label(i + 1)
        date_short = _format_date_short(rec["created"])
        label = f"{mark}  {num}  {rec['size_mb']}MB  •  {date_short}"
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"sel:{i}",
            ),
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"ren:{i}",
            ),
        ])

    # Calculate total size of selection
    total_mb = sum(flat[i]["size_mb"] for i in selections if i < len(flat))
    sel_label = f"📤 Upload Selected ({len(selections)})"
    if total_mb > 0:
        sel_label += f" — {total_mb:.0f} MB"

    buttons.append([InlineKeyboardButton(
        text=sel_label,
        callback_data="upload:confirm",
    )])

    # Select All / Deselect All
    all_selected = len(selections) == len(flat) and len(flat) > 0
    select_label = "☑ Deselect All" if all_selected else "✅ Select All"
    buttons.append([InlineKeyboardButton(
        text=select_label,
        callback_data="sel:all",
    )])

    # Bottom row: Change Date + Cancel
    buttons.append([
        InlineKeyboardButton(text="📅 Change Date", callback_data="date:change"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel:check"),
    ])

    return InlineKeyboardMarkup(buttons)


def _build_recording_checklist(
    results: dict[str, list[dict]],
    scan_label: str = "",
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build the recording selection message and checkbox keyboard."""
    total = sum(len(recs) for recs in results.values())
    if total == 0:
        text = _build_checklist_text(results, scan_label)
        return text, None

    text = _build_checklist_text(results, scan_label)

    flat: list[dict] = []
    for recs in results.values():
        flat.extend(recs)

    keyboard = _build_checklist_keyboard(flat, set())
    return text, keyboard


REAUTH_MESSAGE = """⚠️ **Session Expired**

Your Microsoft refresh token has expired. Follow these steps to recover:

**Step 1:** Run `python scripts/get_teams_token.py` locally on your machine.

**Step 2:** Follow the prompt to open Microsoft Login and enter the device code.

**Step 3:** Copy the outputted `refresh_token` and update the `TEAMS_REFRESH_TOKEN` GitHub Secret in your repository.

**Step 4:** Come back here and send `/check` to verify it works

_This takes less than 2 minutes._"""

# ───────────────────────── handler registration ───────────────────

# In-memory state for recording selections per user
_pending_results: dict[int, dict[str, list[dict]]] = {}  # chat_id → results
_pending_selections: dict[int, set[int]] = {}             # chat_id → selected indices
_flat_recordings: dict[int, list[dict]] = {}              # chat_id → flat list
_rename_overrides: dict[int, dict[int, str]] = {}         # chat_id → {idx: new_name}
_rename_pending: dict[int, int | None] = {}               # chat_id → idx awaiting rename
_upload_cancelled: dict[int, bool] = {}                   # chat_id → cancel flag
_checklist_msg_id: dict[int, int] = {}                    # chat_id → message id of checklist
_scan_context: dict[int, dict] = {}                       # chat_id → {subject_filter, label, ...}
_date_input_pending: dict[int, bool] = {}                 # chat_id → waiting for date input


def register_handlers(
    app: Client,
    on_fetch: Callable,
    on_upload: Callable[[list[dict]], Any],
    owner_chat_id: int | None = None,
) -> None:
    """Register all Telegram command and callback handlers.

    Parameters
    ----------
    app : Client
        The Pyrogram client to register handlers on.
    on_fetch : async callable(subject_filter, date_start, date_end) → dict
        Called to fetch recordings. Returns {subject: [recording_dicts]}.
    on_upload : callable(recordings: list[dict]) → Any
        Called to upload selected recordings.
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
            "**What do you want to check?**\n\n"
            "💡 _Tip: Send a date like_ `2026-04-01` _or range like_\n"
            "`2026-04-01 to 2026-04-07` _to check specific dates._",
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
            "Available commands:\n"
            "/check   — 🔍 Scan for new lecture recordings\n"
            "/reauth  — 🔑 Renew your session if expired\n\n"
            "💡 **Quick access:**\n"
            "• Tap a subject → scans **this week** automatically\n"
            "• Send a date: `2026-04-01`\n"
            "• Send a range: `2026-04-01 to 2026-04-07`\n"
            "• Type `today` or `this week`\n\n"
            "Tap /check to get started.",
            reply_markup=REPLY_KEYBOARD,
        )

    # ── Text message handler ─────────────────────────────────────
    @app.on_message(filters.text & filters.private & ~filters.command(["check", "reauth", "start"]))
    async def handle_text(client: Client, message: Message) -> None:
        if not _is_owner(message):
            return

        chat_id = message.chat.id
        text = message.text.strip()

        # ── Reply keyboard button taps ───────────────────────────
        if text == "🔍 Check Recordings":
            subjects = _load_subjects()
            keyboard = _build_subject_keyboard(subjects)
            await message.reply(
                "**What do you want to check?**\n\n"
                "💡 _Send a date or range to scan specific dates._",
                reply_markup=keyboard,
            )
            log.info("Reply-keyboard /check triggered.")
            return

        if text == "🔑 Reauth":
            await message.reply(REAUTH_MESSAGE)
            log.info("Reply-keyboard /reauth triggered.")
            return

        # ── Check if there's a rename pending ────────────────────
        if chat_id in _rename_pending and _rename_pending[chat_id] is not None:
            idx = _rename_pending[chat_id]
            _rename_pending[chat_id] = None

            new_name = text.strip()
            if not new_name.lower().endswith(".mp4"):
                new_name += ".mp4"

            if chat_id not in _rename_overrides:
                _rename_overrides[chat_id] = {}
            _rename_overrides[chat_id][idx] = new_name

            await message.reply(f"✅ Renamed to: **{new_name}**")

            results = _pending_results.get(chat_id)
            flat = _flat_recordings.get(chat_id, [])
            selections = _pending_selections.get(chat_id, set())
            overrides = _rename_overrides.get(chat_id, {})
            ctx = _scan_context.get(chat_id, {})

            if results and flat and chat_id in _checklist_msg_id:
                try:
                    checklist_text = _build_checklist_text(results, ctx.get("label", ""), overrides)
                    keyboard = _build_checklist_keyboard(flat, selections, overrides)
                    await client.edit_message_text(
                        chat_id=chat_id,
                        message_id=_checklist_msg_id[chat_id],
                        text=checklist_text,
                        reply_markup=keyboard,
                    )
                except MessageNotModified:
                    pass
                except Exception as e:
                    log.warning("Failed to update checklist after rename: %s", e)

            log.info("Renamed recording idx=%d to '%s'", idx, new_name)
            return

        # ── Check if waiting for date input (change date flow) ───
        if _date_input_pending.get(chat_id):
            _date_input_pending[chat_id] = False
            ctx = _scan_context.get(chat_id, {})
            subject_filter = ctx.get("subject_filter")

            parsed = _parse_date_input(text)
            if parsed is None:
                await message.reply(
                    "❌ Couldn't parse that date.\n\n"
                    "Send one of:\n"
                    "• `2026-04-01` — single date\n"
                    "• `2026-04-01 to 2026-04-07` — date range\n"
                    "• `today` or `this week`"
                )
                return

            date_start, date_end, label = parsed

            if date_end:
                valid, err = _validate_date_range(date_start, date_end)
                if not valid:
                    await message.reply(err)
                    return

            label_ctx = f"{subject_filter or 'All Subjects'}"
            await message.reply(f"🔍 Scanning **{label_ctx}** — {label}...")

            try:
                results = await on_fetch(subject_filter, date_start, date_end)
            except Exception as e:
                await message.reply(f"❌ Fetch error: {e}")
                log.error("Fetch failed: %s", e)
                return

            text_reply, keyboard = _build_recording_checklist(results, label)
            _store_results(chat_id, results, subject_filter, label)
            sent = await message.reply(text_reply, reply_markup=keyboard)
            if keyboard:
                _checklist_msg_id[chat_id] = sent.id
            return

        # ── Shortcut keywords ────────────────────────────────────
        text_lower = text.lower().strip()
        if text_lower == "today":
            today_str = datetime.now(timezone.utc).date().isoformat()
            label = f"Today ({_format_date_short(today_str)})"
            await message.reply(f"🔍 Scanning **all subjects** — {label}...")
            try:
                results = await on_fetch(None, today_str, None)
            except Exception as e:
                await message.reply(f"❌ Fetch error: {e}")
                return
            text_reply, keyboard = _build_recording_checklist(results, label)
            _store_results(chat_id, results, None, label)
            sent = await message.reply(text_reply, reply_markup=keyboard)
            if keyboard:
                _checklist_msg_id[chat_id] = sent.id
            return

        if text_lower == "this week":
            mon, sun = _get_current_week_range()
            label = f"This Week ({_format_date_short(mon)} – {_format_date_short(sun)})"
            await message.reply(f"🔍 Scanning **all subjects** — {label}...")
            try:
                results = await on_fetch(None, mon, sun)
            except Exception as e:
                await message.reply(f"❌ Fetch error: {e}")
                return
            text_reply, keyboard = _build_recording_checklist(results, label)
            _store_results(chat_id, results, None, label)
            sent = await message.reply(text_reply, reply_markup=keyboard)
            if keyboard:
                _checklist_msg_id[chat_id] = sent.id
            return

        # ── Date range: YYYY-MM-DD to YYYY-MM-DD ────────────────
        range_match = re.match(
            r"^(\d{4}-\d{2}-\d{2})\s*(?:to|-)\s*(\d{4}-\d{2}-\d{2})$",
            text, re.IGNORECASE,
        )
        if range_match:
            date_start = range_match.group(1)
            date_end = range_match.group(2)
            valid, err = _validate_date_range(date_start, date_end)
            if not valid:
                await message.reply(err)
                return
            label = f"{_format_date_short(date_start)} – {_format_date_short(date_end)}"
            await message.reply(f"🔍 Scanning **all subjects** — {label}...")
            try:
                results = await on_fetch(None, date_start, date_end)
            except Exception as e:
                await message.reply(f"❌ Fetch error: {e}")
                return
            text_reply, keyboard = _build_recording_checklist(results, label)
            _store_results(chat_id, results, None, label)
            sent = await message.reply(text_reply, reply_markup=keyboard)
            if keyboard:
                _checklist_msg_id[chat_id] = sent.id
            return

        # ── Single date: YYYY-MM-DD ──────────────────────────────
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})$", text)
        if date_match:
            date_str = date_match.group(1)
            label = _format_date_short(date_str)
            await message.reply(f"🔍 Scanning **all subjects** — {label}...")
            try:
                results = await on_fetch(None, date_str, None)
            except Exception as e:
                await message.reply(f"❌ Fetch error: {e}")
                log.error("Fetch failed for date '%s': %s", date_str, e)
                return

            text_reply, keyboard = _build_recording_checklist(results, label)
            _store_results(chat_id, results, None, label)
            sent = await message.reply(text_reply, reply_markup=keyboard)
            if keyboard:
                _checklist_msg_id[chat_id] = sent.id
            return

        # ── Normal subject matching ──────────────────────────────
        subjects = _load_subjects()
        matched_subject = None
        for subj in subjects:
            if (text_lower == subj["name"].lower()
                    or text_lower == subj.get("short", "").lower()):
                matched_subject = subj["name"]
                break
            for kw in subj.get("keywords", []):
                if text_lower == kw.lower():
                    matched_subject = subj["name"]
                    break
            if matched_subject:
                break

        if not matched_subject:
            return  # Not a subject — ignore silently

        # Single subject → auto-fetch This Week
        mon, sun = _get_current_week_range()
        label = f"This Week ({_format_date_short(mon)} – {_format_date_short(sun)})"
        await message.reply(f"🔍 Scanning **{matched_subject}** — {label}...")

        try:
            results = await on_fetch(matched_subject, mon, sun)
        except Exception as e:
            await message.reply(f"❌ Fetch error: {e}")
            log.error("Fetch failed for '%s': %s", matched_subject, e)
            return

        text_reply, keyboard = _build_recording_checklist(results, label)
        _store_results(chat_id, results, matched_subject, label)
        sent = await message.reply(text_reply, reply_markup=keyboard)
        if keyboard:
            _checklist_msg_id[chat_id] = sent.id

    # ── Subject button callback ──────────────────────────────────
    @app.on_callback_query(filters.regex(r"^subj:"))
    async def handle_subject_select(client: Client, cb: CallbackQuery) -> None:
        if not _is_owner(cb):
            return

        subject_key = cb.data.split(":", 1)[1]
        chat_id = cb.message.chat.id

        if subject_key == "__ALL__":
            # Check All → Since Last Run
            subject_filter = None
            label = "Since Last Run"
            display = "all subjects"
        else:
            # Single subject → This Week
            subject_filter = subject_key
            mon, sun = _get_current_week_range()
            label = f"This Week ({_format_date_short(mon)} – {_format_date_short(sun)})"
            display = subject_filter

        try:
            await cb.message.edit_text(f"🔍 Scanning **{display}** — {label}...")
        except MessageNotModified:
            pass

        try:
            if subject_filter:
                mon, sun = _get_current_week_range()
                results = await on_fetch(subject_filter, mon, sun)
            else:
                results = await on_fetch(None, None, None)
        except Exception as e:
            try:
                await cb.message.edit_text(f"❌ Fetch error: {e}")
            except MessageNotModified:
                pass
            log.error("Fetch failed: %s", e)
            return

        text, keyboard = _build_recording_checklist(results, label)
        _store_results(chat_id, results, subject_filter, label)
        try:
            await cb.message.edit_text(text, reply_markup=keyboard)
        except MessageNotModified:
            pass
        if keyboard:
            _checklist_msg_id[chat_id] = cb.message.id
        try:
            await cb.answer()
        except Exception:
            pass

    # ── Checkbox toggle callback ─────────────────────────────────
    @app.on_callback_query(filters.regex(r"^sel:"))
    async def handle_select_toggle(client: Client, cb: CallbackQuery) -> None:
        if not _is_owner(cb):
            return

        chat_id = cb.message.chat.id
        action = cb.data.split(":", 1)[1]

        if chat_id not in _pending_selections:
            _pending_selections[chat_id] = set()

        flat = _flat_recordings.get(chat_id, [])
        selections = _pending_selections[chat_id]

        if action == "all":
            if len(selections) == len(flat):
                selections.clear()
            else:
                selections.update(range(len(flat)))
        else:
            idx = int(action)
            if idx in selections:
                selections.discard(idx)
            else:
                selections.add(idx)

        overrides = _rename_overrides.get(chat_id, {})
        keyboard = _build_checklist_keyboard(flat, selections, overrides)

        try:
            await cb.message.edit_reply_markup(reply_markup=keyboard)
        except MessageNotModified:
            pass
        await cb.answer()

    # ── Rename button callback ───────────────────────────────────
    @app.on_callback_query(filters.regex(r"^ren:"))
    async def handle_rename(client: Client, cb: CallbackQuery) -> None:
        if not _is_owner(cb):
            return

        chat_id = cb.message.chat.id
        idx = int(cb.data.split(":", 1)[1])
        flat = _flat_recordings.get(chat_id, [])

        if idx >= len(flat):
            await cb.answer("Invalid recording!", show_alert=True)
            return

        if chat_id in _rename_pending and _rename_pending[chat_id] is not None:
            await cb.message.reply("❌ Rename cancelled.")

        _rename_pending[chat_id] = idx
        overrides = _rename_overrides.get(chat_id, {})
        current_name = overrides.get(idx, flat[idx]["name"])

        await cb.message.reply(
            f"✏️ Send the new name for:\n"
            f"**{current_name}**\n"
            f"_(type without extension — .mp4 will be added automatically)_"
        )
        await cb.answer()

    # ── Change Date callback ─────────────────────────────────────
    @app.on_callback_query(filters.regex(r"^date:change"))
    async def handle_change_date(client: Client, cb: CallbackQuery) -> None:
        if not _is_owner(cb):
            return

        chat_id = cb.message.chat.id
        _date_input_pending[chat_id] = True

        await cb.message.reply(
            "📅 **Change Date**\n\n"
            "Send one of:\n"
            "• `2026-04-01` — single date\n"
            "• `2026-04-01 to 2026-04-07` — date range\n"
            "• `today` — today only\n"
            "• `this week` — current week"
        )
        await cb.answer()

    # ── Cancel callback ──────────────────────────────────────────
    @app.on_callback_query(filters.regex(r"^cancel:check"))
    async def handle_cancel(client: Client, cb: CallbackQuery) -> None:
        if not _is_owner(cb):
            return

        chat_id = cb.message.chat.id
        _clear_state(chat_id)

        try:
            await cb.message.edit_text("❌ **Cancelled.**\n\nSend /check to start again.")
        except MessageNotModified:
            pass
        await cb.answer()

    # ── Upload confirm callback ──────────────────────────────────
    @app.on_callback_query(filters.regex(r"^upload:confirm"))
    async def handle_upload_confirm(client: Client, cb: CallbackQuery) -> None:
        if not _is_owner(cb):
            return

        chat_id = cb.message.chat.id
        selections = _pending_selections.get(chat_id, set())
        flat = _flat_recordings.get(chat_id, [])
        overrides = _rename_overrides.get(chat_id, {})

        if not selections:
            await cb.answer("⚠️ No recordings selected.", show_alert=True)
            return

        selected_recs = []
        for i in sorted(selections):
            if i < len(flat):
                rec = flat[i].copy()
                if i in overrides:
                    rec["name"] = overrides[i]
                selected_recs.append(rec)

        if not selected_recs:
            await cb.answer("Selection invalid — try /check again.", show_alert=True)
            return

        _upload_cancelled[chat_id] = False

        total_mb = sum(r["size_mb"] for r in selected_recs)
        names = "\n".join(f"  📥 {_clean_filename(r['name'])}" for r in selected_recs)
        try:
            await cb.message.edit_text(
                f"**Uploading {len(selected_recs)} recording(s)** ({total_mb:.0f} MB):\n"
                f"{names}\n\n"
                "⏳ Starting upload..."
            )
        except MessageNotModified:
            pass

        try:
            on_upload(selected_recs)
        except Exception as e:
            await cb.message.reply(f"❌ Upload error: {e}")
            log.error("Upload failed: %s", e)
        finally:
            _clear_state(chat_id)

        await cb.answer()


def _parse_date_input(text: str) -> tuple[str, str | None, str] | None:
    """Parse user date input. Returns (date_start, date_end_or_None, label) or None."""
    text = text.strip().lower()

    if text == "today":
        today_str = datetime.now(timezone.utc).date().isoformat()
        return today_str, None, f"Today ({_format_date_short(today_str)})"

    if text == "this week":
        mon, sun = _get_current_week_range()
        return mon, sun, f"This Week ({_format_date_short(mon)} – {_format_date_short(sun)})"

    # Date range
    range_match = re.match(
        r"^(\d{4}-\d{2}-\d{2})\s*(?:to|-)\s*(\d{4}-\d{2}-\d{2})$",
        text, re.IGNORECASE,
    )
    if range_match:
        ds, de = range_match.group(1), range_match.group(2)
        return ds, de, f"{_format_date_short(ds)} – {_format_date_short(de)}"

    # Single date
    date_match = re.match(r"^(\d{4}-\d{2}-\d{2})$", text)
    if date_match:
        ds = date_match.group(1)
        return ds, None, _format_date_short(ds)

    return None


def _store_results(
    chat_id: int,
    results: dict[str, list[dict]],
    subject_filter: str | None = None,
    label: str = "",
) -> None:
    """Store fetch results and scan context for selection and date change."""
    _pending_results[chat_id] = results
    _pending_selections[chat_id] = set()
    _rename_overrides[chat_id] = {}
    _rename_pending[chat_id] = None
    _upload_cancelled[chat_id] = False
    _date_input_pending[chat_id] = False

    flat: list[dict] = []
    for recs in results.values():
        flat.extend(recs)
    _flat_recordings[chat_id] = flat

    _scan_context[chat_id] = {
        "subject_filter": subject_filter,
        "label": label,
    }


def _clear_state(chat_id: int) -> None:
    """Clear all in-memory state for a chat."""
    _pending_results.pop(chat_id, None)
    _pending_selections.pop(chat_id, None)
    _flat_recordings.pop(chat_id, None)
    _rename_overrides.pop(chat_id, None)
    _rename_pending.pop(chat_id, None)
    _upload_cancelled.pop(chat_id, None)
    _checklist_msg_id.pop(chat_id, None)
    _scan_context.pop(chat_id, None)
    _date_input_pending.pop(chat_id, None)


# ───────────────────────── startup warnings ───────────────────────

async def send_startup_warnings(client: Client, chat_id: int) -> None:
    """Send one-time startup warnings to the owner."""
    gh_pat = os.environ.get("GH_PAT", "")
    if not gh_pat:
        try:
            await client.send_message(
                chat_id,
                "⚠️ **GH_PAT secret is not set.**\n"
                "refresh_token will NOT auto-rotate.\n"
                "Update GH_PAT in GitHub Secrets to enable auto-rotation.",
            )
            log.warning("GH_PAT not set — startup warning sent to Telegram.")
        except Exception as e:
            log.warning("Failed to send GH_PAT warning: %s", e)
