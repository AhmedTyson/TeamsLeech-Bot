"""Download a recording straight from a shared link into the review queue.

Owner sends a Teams/SharePoint link in the DM; the bot downloads the video,
drops it into the DM like any scanned upload, and asks which subject it
belongs to so numbering and topic routing stay consistent. Publishing is
still only the owner's Publish tap.
"""

import logging
import os

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from teamsleech.core.config import settings
from teamsleech.models.domain import UploadedItem
from teamsleech.services.scanner import ScannerService, subject_key
from teamsleech.services.shares import extract_recording_link, resolve_share_recording
from teamsleech.services.state import StateManager
from teamsleech.services.transfer import TransferService
from teamsleech.services.triage import propose_name
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_edit_text

log = logging.getLogger("link_download")

LINK_SUBJ_PREFIX = "linksubj:"


def assign_subject_to_upload(item: UploadedItem, subject) -> None:
    """Number and name a link-downloaded upload for the chosen subject."""
    n = subject.next_no
    ext = os.path.splitext(item.name)[1]
    item.subject_name = subject_key(subject)
    item.assigned_no = n
    item.name = propose_name(subject, n) + ext


def build_link_subject_keyboard(subjects) -> InlineKeyboardMarkup:
    buttons, row = [], []
    for s in subjects:
        row.append(
            InlineKeyboardButton(
                text=s.short or s.name,
                callback_data=f"{LINK_SUBJ_PREFIX}{subject_key(s)}",
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton("⏭ Skip (no subject)", callback_data=f"{LINK_SUBJ_PREFIX}__skip__")
    ])
    return InlineKeyboardMarkup(buttons)


def register_link_download(
    app: Client, transfer: TransferService, state: StateManager, scanner: ScannerService
) -> None:
    @app.on_message(filters.private & owner_only & filters.text)
    async def handle_recording_link(client: Client, message: Message):
        url = extract_recording_link(message.text)
        if not url:
            return

        status = await message.reply("🔗 **Link received** — resolving the file...")
        try:
            rec = await resolve_share_recording(transfer.graph, url)
        except Exception as e:
            await safe_edit_text(
                status,
                "❌ Could not read that link. Make sure it's a SharePoint/"
                f"OneDrive recording link you can open.\n`{e}`",
            )
            return

        await safe_edit_text(status, f"⬇️ Downloading **{rec.name}** ({rec.size_mb} MB)...")

        async def progress(event, data):
            if event == "file_progress" and data.get("percent", 0) % 20 == 0:
                await safe_edit_text(
                    status,
                    f"⬇️ **{rec.name}** — {data['percent']}%"
                    f" ({data.get('speed_mbps', 0):.1f} MB/s)",
                )

        results = await transfer.upload_recordings([rec], progress)
        ok = [r for r in results if r.get("success") and r.get("message_id")]
        if not ok:
            err = results[0].get("error") if results else "unknown"
            from teamsleech.tg_bot.handlers.upload_ui import _failure_keyboard
            from teamsleech.tg_bot.retry_failed import record_failed

            record_failed(state, settings.telegram_chat_id, rec)
            await safe_edit_text(
                status,
                f"❌ Download failed: {err}",
                reply_markup=_failure_keyboard(err),
            )
            return

        session = state.get_session(settings.telegram_chat_id)
        session.last_uploads.append(
            UploadedItem(
                name=rec.name,
                message_id=ok[0]["message_id"],
                chat_id=ok[0]["chat_id"],
                subject_name="",
                created=rec.created,
                time=rec.time,
                is_video=rec.is_video,
            )
        )

        subjects = scanner.load_subjects()
        if subjects:
            await safe_edit_text(
                status,
                f"✅ **{rec.name}** is in this DM.\n"
                "Pick its subject so it gets a number and topic:",
                reply_markup=build_link_subject_keyboard(subjects),
            )
        else:
            await safe_edit_text(
                status,
                f"✅ **{rec.name}** is in this DM. No subjects configured yet.",
            )

    @app.on_callback_query(filters.regex(rf"^{LINK_SUBJ_PREFIX}") & owner_only)
    async def handle_link_subject(client: Client, cb):
        key = cb.data[len(LINK_SUBJ_PREFIX):]
        session = state.get_session(cb.message.chat.id)
        pending = next((u for u in session.last_uploads if not u.subject_name), None)
        if not pending:
            await cb.answer("Nothing waiting for a subject.", show_alert=True)
            return
        if key == "__skip__":
            await safe_edit_text(
                cb.message,
                f"⏭ **{pending.name}** kept without a subject — it won't"
                " publish until you assign one.",
            )
            await cb.answer()
            return
        subjects = scanner.load_subjects()
        subj = next((s for s in subjects if subject_key(s) == key), None)
        if not subj:
            await cb.answer("Unknown subject.", show_alert=True)
            return
        assign_subject_to_upload(pending, subj)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"📤 Publish {len(session.last_uploads)} to group",
                callback_data="pub:group",
            )
        ]])
        await safe_edit_text(
            cb.message,
            f"✅ Numbered as **{pending.name}**\nReady to publish when you are.",
            reply_markup=kb,
        )
        await cb.answer()
