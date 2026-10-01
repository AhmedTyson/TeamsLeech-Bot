import asyncio
import logging
import os

from pyrogram.client import Client
from pyrogram.methods.utilities.idle import idle

from teamsleech.core.config import settings
from teamsleech.services.auth import TokenExpiredError, authenticate
from teamsleech.services.discovery import DiscoveryService
from teamsleech.services.graph import GraphClient
from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.services.transfer import TransferService
from teamsleech.tg_bot.handlers import register_all_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-14s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


async def _build_upload_client() -> Client | None:
    if not settings.telegram_session_string:
        return None
    log.info("User session configured: large uploads up to 2 GB.")
    client = Client(
        name="teamsleech_user",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telegram_session_string,
        in_memory=True,
    )
    await client.start()
    return client


async def _run_auto_check(
    scanner_service: ScannerService,
    state_manager: StateManager,
    app: Client,
) -> None:
    log.info("Running automated scheduled check...")

    subject_filter = os.getenv("SUBJECT_NAME") or None
    if subject_filter:
        log.info("Filtering to single subject: %s", subject_filter)

    try:
        results = await scanner_service.scan_recordings(subject_filter, None, None)
        total = sum(len(recs) for recs in results.values())
        if total > 0:
            from teamsleech.tg_bot.keyboards import build_checklist_keyboard
            from teamsleech.tg_bot.views import build_checklist_text, escape_markdown

            label = "Since Last Run"
            session = state_manager.get_session(settings.telegram_chat_id)
            session.pending_recordings = [r for recs in results.values() for r in recs]
            session.scan_label = label

            text = build_checklist_text(results, label)
            unmatched = getattr(scanner_service, "last_unmatched", None)
            if isinstance(unmatched, list) and unmatched:
                names = ", ".join(escape_markdown(t.display_name) for t in unmatched[:10])
                text += f"\n\n⚠️ _Teams not tracked by any subject ({len(unmatched)}): {names}_"
            keyboard = build_checklist_keyboard(
                session.pending_recordings, session.selected_indices
            )

            await app.send_message(settings.telegram_chat_id, text, reply_markup=keyboard)
            log.info("Auto-check found %d recordings, notification sent.", total)
        else:
            log.info("Auto-check found 0 new recordings. Staying completely silent.")
    except Exception:
        log.exception("Scheduled check failed")


async def _run_reauth_mode(app: Client) -> None:
    """Guided sign-in; raises SystemExit(1) when it fails."""
    from teamsleech.services.reauth import run_reauth_flow

    await app.start()
    reauthed = await run_reauth_flow(app, settings.telegram_chat_id)
    if not reauthed:
        await app.stop()
        raise SystemExit(1)


def main() -> None:
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

    async def _run() -> None:
        # 2. Authenticate & Rotate Secret (or guided reauth)
        log.info("Step 1/3: Authenticating with Microsoft & GitHub...")
        if os.getenv("MODE") == "reauth":
            await _run_reauth_mode(app)
        try:
            access_token = await authenticate()
        except TokenExpiredError:
            log.critical(
                "Microsoft session expired. Re-run the workflow with "
                "mode=reauth (guided Telegram sign-in), or update "
                "TEAMS_REFRESH_TOKEN via scripts/get_teams_token.py."
            )
            return
        except Exception as e:
            log.critical(f"Auth failed: {e}")
            return

        # 3. Initialize Services
        log.info("Step 2/3: Initializing core services...")
        graph_client = GraphClient(access_token)
        state_manager = StateManager(app, settings.telegram_chat_id)
        discovery_service = DiscoveryService(graph_client)
        upload_client = await _build_upload_client()
        scanner_service = ScannerService(graph_client, state_manager)
        transfer_service = TransferService(
            graph_client,
            state_manager,
            app,
            settings.telegram_chat_id,
            upload_client,
        )

        # 4. Register Handlers
        register_all_handlers(
            app,
            scanner=scanner_service,
            transfer=transfer_service,
            state=state_manager,
            discovery=discovery_service,
        )

        if not app.is_connected:
            await app.start()
        await state_manager.initialize()

        log.info("Step 3/3: Bot is live and listening.")

        # 5. Scheduled Auto-Check Logic (Silent Mode)
        if settings.auto_check == "1":
            await _run_auto_check(scanner_service, state_manager, app)

        auto = settings.auto_check == "1"
        interactive = os.getenv("INTERACTIVE") == "1"
        if auto and not interactive:
            log.info("Auto-check complete, exiting.")
        else:
            # Stay for Telegram input, bounded so the run exits cleanly
            # instead of hitting the workflow timeout as a failure.
            log.info("Listening for Telegram input (up to 45 min).")
            try:
                await asyncio.wait_for(idle(), timeout=45 * 60)  # type: ignore[no-untyped-call]
            except TimeoutError:
                log.info("Interactive window elapsed, exiting.")

        # Cleanup
        await graph_client.close()
        if upload_client is not None:
            await upload_client.stop()
        await app.stop()

    app.run(_run())


if __name__ == "__main__":
    main()
