import asyncio
import logging
from typing import Any

from pyrogram.client import Client
from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified
from pyrogram.types import Message

from teamsleech.services.discovery import DiscoveryService
from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.services.transfer import TransferService

log = logging.getLogger("tg_handlers")


async def safe_edit_text(message: Message | None, text: str, **kwargs: Any) -> None:
    if message is None:
        return
    try:
        await message.edit_text(text, **kwargs)
    except MessageNotModified:
        pass
    except MessageIdInvalid:
        log.warning("safe_edit_text: message id invalid, skipping edit.")
    except FloodWait as e:
        try:
            await asyncio.sleep(min(int(getattr(e, "value", 1)), 60))
            await message.edit_text(text, **kwargs)
        except (MessageNotModified, MessageIdInvalid, FloodWait):
            pass


from .actions_ui import register_actions_ui  # noqa: E402
from .commands import register_commands  # noqa: E402
from .scanner_ui import register_scanner_ui  # noqa: E402
from .search_inputs import register_search_inputs  # noqa: E402
from .upload_ui import register_upload_ui  # noqa: E402


def register_all_handlers(
    app: Client,
    scanner: ScannerService,
    transfer: TransferService,
    state: StateManager,
    discovery: DiscoveryService,
) -> None:
    """
    Registers all modular Telegram handlers to the Pyrogram client.
    """
    register_commands(app, scanner, state, discovery)
    register_search_inputs(app, discovery, state)
    register_scanner_ui(app, scanner, state)
    register_upload_ui(app, transfer, state, scanner)
    register_actions_ui(app)
