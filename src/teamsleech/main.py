import os
import sys
import asyncio
import logging

from pyrogram import Client

from teamsleech.core.config import settings
from teamsleech.services.auth import authenticate, TokenExpiredError
from teamsleech.services.graph import GraphClient
from teamsleech.services.state import StateManager
from teamsleech.services.discovery import DiscoveryService
from teamsleech.services.scanner import ScannerService
from teamsleech.services.transfer import TransferService
from teamsleech.tg_bot.handlers import register_all_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-14s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

def main():
    log.info("=" * 50)
    log.info("TeamsLeech Modern App — Booting")
    log.info("=" * 50)

    # 1. Initialize Pyrogram Client
    app = Client(
        name="teamsleech_bot",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        bot_token=settings.telegram_bot_token,
        in_memory=True,
    )

    async def _run():
        # 2. Authenticate & Rotate Secret
        log.info("Step 1/3: Authenticating with Microsoft & GitHub...")
        try:
            access_token = await authenticate()
        except TokenExpiredError:
            log.critical("Microsoft session expired. Please run local setup script and update TEAMS_REFRESH_TOKEN secret.")
            # Start dummy bot mode to send alert if possible?
            return
        except Exception as e:
            log.critical(f"Auth failed: {e}")
            return
            
        # 3. Initialize Services
        log.info("Step 2/3: Initializing core services...")
        graph_client = GraphClient(access_token)
        state_manager = StateManager(app, settings.telegram_chat_id)
        discovery_service = DiscoveryService(graph_client)
        scanner_service = ScannerService(graph_client, state_manager)
        transfer_service = TransferService(graph_client, state_manager, app, settings.telegram_chat_id)
        
        # 4. Register Handlers
        register_all_handlers(
            app,
            scanner=scanner_service,
            transfer=transfer_service,
            state=state_manager,
            discovery=discovery_service
        )
        
        await app.start()
        await state_manager.initialize()
        
        log.info("Step 3/3: Bot is live and listening.")
        
        # 5. Scheduled Auto-Check Logic (Silent Mode)
        if settings.auto_check == "1":
            log.info("Running automated scheduled check...")

            subject_filter = os.getenv("SUBJECT_NAME") or None
            if subject_filter:
                log.info("Filtering to single subject: %s", subject_filter)

            try:
                results = await scanner_service.scan_recordings(subject_filter, None, None)
                total = sum(len(recs) for recs in results.values())
                if total > 0:
                    from teamsleech.tg_bot.views import build_checklist_text
                    from teamsleech.tg_bot.keyboards import build_checklist_keyboard

                    label = "Since Last Run"
                    session = state_manager.get_session(settings.telegram_chat_id)
                    session.pending_recordings = [r for recs in results.values() for r in recs]
                    session.scan_label = label

                    text = build_checklist_text(results, label)
                    keyboard = build_checklist_keyboard(session.pending_recordings, session.selected_indices)

                    await app.send_message(settings.telegram_chat_id, text, reply_markup=keyboard)
                    log.info("Auto-check found %d recordings, notification sent.", total)
                else:
                    log.info("Auto-check found 0 new recordings. Staying completely silent.")
            except Exception as e:
                log.error("Scheduled check failed: %s", e)

        from pyrogram import idle
        await idle()
        
        # Cleanup
        await graph_client.close()
        await app.stop()

    app.run(_run())

if __name__ == "__main__":
    main()
