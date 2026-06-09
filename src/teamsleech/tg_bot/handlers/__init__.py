from pyrogram import Client

from services.scanner import ScannerService
from services.transfer import TransferService
from services.state import StateManager
from services.discovery import DiscoveryService

from .commands import register_commands
from .search_inputs import register_search_inputs
from .scanner_ui import register_scanner_ui
from .upload_ui import register_upload_ui

def register_all_handlers(
    app: Client,
    scanner: ScannerService,
    transfer: TransferService,
    state: StateManager,
    discovery: DiscoveryService
) -> None:
    """
    Registers all modular Telegram handlers to the Pyrogram client.
    """
    register_commands(app, scanner, state, discovery)
    register_search_inputs(app, discovery, state)
    register_scanner_ui(app, scanner, state)
    register_upload_ui(app, transfer, state, scanner)
