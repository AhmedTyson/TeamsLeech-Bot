"""Forward-a-file fallback: owner sends a downloaded recording to the DM.

When SharePoint downloads are blocked, the owner can download the video in
his own browser and send/forward the file here. The bot registers the
Telegram message itself as the review item — no download, no re-upload —
so Bot API file-size limits never apply (publishing later uses a
server-side copy_message). Numbering, subject routing and the publish tap
behave exactly like a link download.
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from teamsleech.models.domain import UploadedItem
from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers.link_download import build_link_subject_keyboard

log = logging.getLogger("file_drop")


def describe_media(message: Message) -> tuple[str, str] | None:
    """(file name, kind) for video/audio/document messages, else None."""
    if message.video:
        return message.video.file_name or "video.mp4", "video"
    if message.audio:
        return message.audio.file_name or "audio.m4a", "audio"
    if message.document:
        return message.document.file_name or "file", "document"
    return None


def register_file_drop(
    app: Client, state: StateManager, scanner: ScannerService
) -> None:
    @app.on_message(
        filters.private
        & owner_only
        & (filters.video | filters.audio | filters.document)
    )
    async def handle_dropped_file(client: Client, message: Message):
        media = describe_media(message)
        if not media:
            return
        name, kind = media

        session = state.get_session(message.chat.id)
        # Telegram may re-deliver a message; never register it twice.
        if any(
            u.message_id == message.id and u.chat_id == message.chat.id
            for u in session.last_uploads
        ):
            return

        created = message.date.isoformat() if message.date else ""
        session.last_uploads.append(
            UploadedItem(
                name=name,
                message_id=message.id,
                chat_id=message.chat.id,
                subject_name="",
                created=created,
                time="",
                is_video=(kind == "video"),
            )
        )
        log.info("Registered dropped file %s (msg %s)", name, message.id)

        subjects = scanner.load_subjects()
        if subjects:
            await message.reply(
                f"📥 **{name}** received.\n"
                "Pick its subject so it gets a number and topic:",
                reply_markup=build_link_subject_keyboard(subjects),
            )
        else:
            await message.reply(
                f"📥 **{name}** received. No subjects configured yet."
            )
