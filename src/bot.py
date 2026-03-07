"""
Phase 3 — bot

Telegram bot interface for TeamsLeech using Pyrogram.
Handles /check (subject buttons), text commands, /reauth recovery,
multi-select recording checkboxes, rename, select all, and cancel workflow.

This module does NOT call fetcher.py or uploader.py directly.
It exposes handler functions that the orchestrator (main.py, Phase 5)
will wire up with the actual fetcher and uploader.

Public API
----------
create_bot()       → pyrogram.Client  (configured, not started)
register_handlers(app, on_fetch, on_upload) → None
"""

import asyncio
import os
import json
import logging
import re
import requests as http_requests
from typing import Callable, Any

from pyrogram import Client, filters
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
        [KeyboardButton("⛔ Cancel Workflow")],
    ],
    resize_keyboard=True,
)

log = logging.getLogger("bot")

# ───────────────────────── constants ──────────────────────────

DIVIDER = "─────────────────────────────"

# Emoji number labels: 1️⃣ through 🔟, then fallback to plain digits
_NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

def _num_label(n: int) -> str:
    """Return emoji number for 1-based index n."""
    if 1 <= n <= 10:
        return _NUM_EMOJI[n - 1]
    return f"**{n}.**"


def _clean_filename(name: str) -> str:
    """Remove redundant '-Meeting Recording' suffix from filename."""
    return re.sub(r"-Meeting Recording", "", name)


# ───────────────────────── config ─────────────────────────────────

def _load_subjects(path: str = "subjects_config.json") -> list[dict]:
    """Load subjects from JSON config (shared with fetcher)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("subjects", [])

# ───────────────────────── bot factory ────────────────────────────

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

# ───────────────────────── UI builders ────────────────────────────

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


def _build_checklist_text(
    results: dict[str, list[dict]],
    rename_overrides: dict[int, str] | None = None,
) -> str:
    """Build the checklist message text with numbered, separated recordings.

    If the full listing exceeds Telegram's 4096-char limit, falls back
    to a compact format showing only subject counts.
    """
    total = sum(len(recs) for recs in results.values())

    if total == 0:
        subjects_checked = ", ".join(results.keys())
        return f"No new recordings found for {subjects_checked} ✅"

    overrides = rename_overrides or {}
    lines: list[str] = []
    idx = 0

    for subj_name, recs in results.items():
        if not recs:
            lines.append(f"\n📚 **{subj_name}** — No new recordings ✅")
            continue

        lines.append(f"\n📚 **{subj_name}** — {len(recs)} recording(s)")
        lines.append(DIVIDER)

        for rec_i, rec in enumerate(recs):
            display_name = _clean_filename(overrides.get(idx, rec["name"]))
            num = _num_label(rec_i + 1)

            lines.append(
                f"\n{num}  📅 {rec['created']}   💾 {rec['size_mb']}MB\n"
                f"👥 {rec['team_name']}\n"
                f"📄 {display_name}"
            )
            lines.append(f"\n{DIVIDER}")
            idx += 1

    full_text = "**New recordings found:**\n" + "\n".join(lines)

    # Telegram message limit is 4096 chars — fall back to compact view
    if len(full_text) > 4000:
        compact: list[str] = [f"**{total} new recording(s) found:**"]
        for subj_name, recs in results.items():
            if recs:
                compact.append(f"📚 **{subj_name}** — {len(recs)} file(s)")
            else:
                compact.append(f"📚 **{subj_name}** — ✅")
        compact.append("\n_Use the buttons below to select & upload._")
        return "\n".join(compact)

    return full_text


def _build_checklist_keyboard(
    flat: list[dict],
    selections: set[int],
    rename_overrides: dict[int, str] | None = None,
) -> InlineKeyboardMarkup:
    """Build the checkbox + rename + upload + select-all keyboard.

    Each button row:  ☐ 1️⃣ 331.8MB • 2026-02-26  [✏️]
    Bottom rows:      [ 📤 Upload Selected (N) ]
                      [ ✅ Select All ]
    """
    overrides = rename_overrides or {}
    buttons: list[list[InlineKeyboardButton]] = []

    for i, rec in enumerate(flat):
        mark = "☑" if i in selections else "☐"
        num = _num_label(i + 1)
        label = f"{mark}  {num}  {rec['size_mb']}MB  •  {rec['created']}"
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

    # Upload Selected button with count
    buttons.append([InlineKeyboardButton(
        text=f"📤 Upload Selected ({len(selections)})",
        callback_data="upload:confirm",
    )])
    # Select All button
    all_selected = len(selections) == len(flat) and len(flat) > 0
    select_label = "☑ Deselect All" if all_selected else "✅ Select All"
    buttons.append([InlineKeyboardButton(
        text=select_label,
        callback_data="sel:all",
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
        subjects_checked = ", ".join(results.keys())
        return f"No new recordings found for {subjects_checked} ✅", None

    text = _build_checklist_text(results)

    # Build flat list for keyboard
    flat: list[dict] = []
    for recs in results.values():
        flat.extend(recs)

    keyboard = _build_checklist_keyboard(flat, set())
    return text, keyboard


REAUTH_MESSAGE = """⚠️ **Session Expired**

Your Microsoft refresh token has expired. Follow these steps to recover:

**Step 1:** Open Teams in your browser → Press F12 → Network tab → log in

**Step 2:** Find the `login.microsoftonline.com` POST request → copy `refresh_token` from the request body

**Step 3:** Go to your GitHub repo → Settings → Secrets → Update `TEAMS_REFRESH_TOKEN` with the new token

**Step 4:** Come back here and send `/check` to verify it works

_This takes less than 5 minutes._"""

# ───────────────────────── handler registration ───────────────────

# In-memory state for recording selections per user
_pending_results: dict[int, dict[str, list[dict]]] = {}  # chat_id → results
_pending_selections: dict[int, set[int]] = {}             # chat_id → selected indices
_flat_recordings: dict[int, list[dict]] = {}              # chat_id → flat list
_rename_overrides: dict[int, dict[int, str]] = {}         # chat_id → {idx: new_name}
_rename_pending: dict[int, int | None] = {}               # chat_id → idx awaiting rename
_upload_cancelled: dict[int, bool] = {}                   # chat_id → cancel flag
_checklist_msg_id: dict[int, int] = {}                    # chat_id → message id of checklist
_workflow_active: dict[int, bool] = {}                    # chat_id → workflow running flag


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
            "Available commands:\n"
            "/check   — 🔍 Scan for new lecture recordings\n"
            "/reauth  — 🔑 Renew your session if expired\n\n"
            "Tap /check to get started.",
            reply_markup=REPLY_KEYBOARD,
        )

    # ── Text message — match subject name OR handle rename ───────
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
                "**What do you want to check?**",
                reply_markup=keyboard,
            )
            log.info("Reply-keyboard /check triggered.")
            return

        if text == "🔑 Reauth":
            await message.reply(REAUTH_MESSAGE)
            log.info("Reply-keyboard /reauth triggered.")
            return

        if text == "⛔ Cancel Workflow":
            await _handle_cancel_workflow(client, message)
            return

        # ── Check if there's a rename pending ────────────────────
        if chat_id in _rename_pending and _rename_pending[chat_id] is not None:
            idx = _rename_pending[chat_id]
            _rename_pending[chat_id] = None  # clear pending

            # Add .mp4 if not present
            new_name = text.strip()
            if not new_name.lower().endswith(".mp4"):
                new_name += ".mp4"

            # Store the rename override
            if chat_id not in _rename_overrides:
                _rename_overrides[chat_id] = {}
            _rename_overrides[chat_id][idx] = new_name

            await message.reply(f"✅ Renamed to: **{new_name}**")

            # Update the checklist message with the new name
            results = _pending_results.get(chat_id)
            flat = _flat_recordings.get(chat_id, [])
            selections = _pending_selections.get(chat_id, set())
            overrides = _rename_overrides.get(chat_id, {})

            if results and flat and chat_id in _checklist_msg_id:
                try:
                    checklist_text = _build_checklist_text(results, overrides)
                    keyboard = _build_checklist_keyboard(flat, selections, overrides)
                    await client.edit_message_text(
                        chat_id=chat_id,
                        message_id=_checklist_msg_id[chat_id],
                        text=checklist_text,
                        reply_markup=keyboard,
                    )
                except Exception as e:
                    log.warning("Failed to update checklist after rename: %s", e)

            log.info("Renamed recording idx=%d to '%s'", idx, new_name)
            return

        # ── Normal subject matching ──────────────────────────────
        subjects = _load_subjects()
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

        text_reply, keyboard = _build_recording_checklist(results)
        _store_results(chat_id, results)
        sent = await message.reply(text_reply, reply_markup=keyboard)
        if keyboard:
            _checklist_msg_id[chat_id] = sent.id

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
        if keyboard:
            _checklist_msg_id[chat_id] = cb.message.id
        try:
            await cb.answer()
        except Exception:
            pass  # callback query expired during long fetch — harmless

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
            # Toggle all: if all selected → deselect all, else select all
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

        # Rebuild keyboard with updated check/uncheck marks
        overrides = _rename_overrides.get(chat_id, {})
        keyboard = _build_checklist_keyboard(flat, selections, overrides)

        await cb.message.edit_reply_markup(reply_markup=keyboard)
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

        # Cancel previous rename if active
        if chat_id in _rename_pending and _rename_pending[chat_id] is not None:
            await cb.message.reply("❌ Rename cancelled.")

        # Set new rename pending
        _rename_pending[chat_id] = idx
        overrides = _rename_overrides.get(chat_id, {})
        current_name = overrides.get(idx, flat[idx]["name"])

        await cb.message.reply(
            f"✏️ Send the new name for:\n"
            f"**{current_name}**\n"
            f"_(type without extension — .mp4 will be added automatically)_"
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
        overrides = _rename_overrides.get(chat_id, {})

        if not selections:
            await cb.answer("⚠️ No recordings selected.", show_alert=True)
            return

        selected_recs = []
        for i in sorted(selections):
            if i < len(flat):
                rec = flat[i].copy()
                # Apply rename override if present
                if i in overrides:
                    rec["name"] = overrides[i]
                selected_recs.append(rec)

        if not selected_recs:
            await cb.answer("Selection invalid — try /check again.", show_alert=True)
            return

        # Reset cancel flag and mark workflow as active
        _upload_cancelled[chat_id] = False
        _workflow_active[chat_id] = True

        # Confirm selection
        names = "\n".join(f"  📥 {_clean_filename(r['name'])}" for r in selected_recs)
        await cb.message.edit_text(
            f"**Uploading {len(selected_recs)} recording(s):**\n{names}\n\n"
            "Starting upload..."
        )

        try:
            on_upload(selected_recs)
        except Exception as e:
            await cb.message.reply(f"❌ Upload error: {e}")
            log.error("Upload failed: %s", e)
        finally:
            # Clean up state
            _workflow_active.pop(chat_id, None)
            _pending_results.pop(chat_id, None)
            _pending_selections.pop(chat_id, None)
            _flat_recordings.pop(chat_id, None)
            _rename_overrides.pop(chat_id, None)
            _rename_pending.pop(chat_id, None)
            _checklist_msg_id.pop(chat_id, None)
            _upload_cancelled.pop(chat_id, None)

        await cb.answer()

    # ── Cancel Workflow handler (reply keyboard) ─────────────────
    async def _handle_cancel_workflow(client: Client, message: Message) -> None:
        """Handle ⛔ Cancel Workflow reply-keyboard tap."""
        chat_id = message.chat.id

        # Check if a workflow is active
        if not _workflow_active.get(chat_id, False):
            info_msg = await message.reply("ℹ️ No active workflow to cancel.")
            # Auto-delete after 4 seconds
            await asyncio.sleep(4)
            try:
                await info_msg.delete()
                await message.delete()
            except Exception:
                pass
            return

        # Mark cancelled — upload loop checks this flag
        _upload_cancelled[chat_id] = True
        _workflow_active[chat_id] = False

        # Try to cancel GitHub Actions run
        gh_pat = os.environ.get("GH_PAT", "")
        gh_repo = os.environ.get("GITHUB_REPOSITORY", "")

        api_ok = False
        if gh_pat and gh_repo:
            try:
                # Try to find and cancel the latest in-progress run
                headers = {
                    "Authorization": f"Bearer {gh_pat}",
                    "Accept": "application/vnd.github+json",
                }
                runs_url = f"https://api.github.com/repos/{gh_repo}/actions/runs?status=in_progress&per_page=1"
                resp = http_requests.get(runs_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    runs = resp.json().get("workflow_runs", [])
                    if runs:
                        run_id = runs[0]["id"]
                        cancel_url = f"https://api.github.com/repos/{gh_repo}/actions/runs/{run_id}/cancel"
                        cancel_resp = http_requests.post(cancel_url, headers=headers, timeout=10)
                        if cancel_resp.status_code in (202, 204):
                            await message.reply(
                                f"⛔ **Workflow cancelled.**\n"
                                f"Run #{run_id} has been stopped.\n"
                                f"Any uploads in progress have been halted."
                            )
                            api_ok = True
                            log.info("Cancelled GitHub Actions run #%d", run_id)
            except Exception as exc:
                log.warning("GitHub Actions cancel API failed: %s", exc)

        if not api_ok:
            await message.reply(
                "⚠️ **Local upload stopped.**\n"
                "Could not reach GitHub API — cancel manually:\n"
                f"github.com/{gh_repo}/actions" if gh_repo
                else "⚠️ **Local upload stopped.**\n"
                     "GH_PAT / GITHUB_REPOSITORY not configured."
            )

        # Clean up all state
        _pending_results.pop(chat_id, None)
        _pending_selections.pop(chat_id, None)
        _flat_recordings.pop(chat_id, None)
        _rename_overrides.pop(chat_id, None)
        _rename_pending.pop(chat_id, None)
        _checklist_msg_id.pop(chat_id, None)

        log.info("Workflow cancelled by user (chat_id=%d)", chat_id)


def _store_results(chat_id: int, results: dict[str, list[dict]]) -> None:
    """Store fetch results and build flat recording list for selection."""
    _pending_results[chat_id] = results
    _pending_selections[chat_id] = set()
    _rename_overrides[chat_id] = {}
    _rename_pending[chat_id] = None
    _upload_cancelled[chat_id] = False

    flat: list[dict] = []
    for recs in results.values():
        flat.extend(recs)
    _flat_recordings[chat_id] = flat
