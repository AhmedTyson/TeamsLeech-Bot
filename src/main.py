"""
Phase 5 — main (orchestrator)

Single entry point that wires all modules together:
    token_manager → fetcher → bot → uploader

Reads all secrets from environment variables (set by GitHub Actions
or local .env), creates the Pyrogram bot client, registers handlers
with real fetcher and uploader callbacks, and starts polling.

Usage
-----
    python src/main.py          # local (uses .env)
    # — or inside GitHub Actions workflow (env vars injected)
"""

import os
import sys
import asyncio
import logging

# Ensure the src/ directory is on the path for sibling imports
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()  # no-op if no .env file exists (e.g. in Actions)

from token_manager import (
    exchange_refresh_token,
    rotate_github_secret,
    TokenExpiredError,
    TokenManagerError,
)
from fetcher import fetch_recordings, save_last_run, load_subjects
from bot import create_bot, register_handlers, send_startup_warnings
from uploader import upload_recordings

# ───────────────────────── logging ──────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-14s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

# ───────────────────────── config ─────────────────────────────────

SUBJECTS_PATH = os.environ.get("SUBJECTS_PATH", "subjects_config.json")
STATE_DIR = os.environ.get("STATE_DIR", ".state")

# ───────────────────────── env validation ───────────────────────

REQUIRED_ENV = [
    "TEAMS_REFRESH_TOKEN",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_SESSION",
    "TELEGRAM_CHAT_ID",
]


def _validate_env() -> dict[str, str]:
    """Check all required env vars are present. Returns them as a dict."""
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        log.critical("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)

    env = {v: os.environ[v].strip() for v in REQUIRED_ENV}
    log.info("All %d required env vars present.", len(REQUIRED_ENV))
    return env

# ───────────────────────── auth ───────────────────────────────────

def _authenticate(env: dict[str, str]) -> str:
    """Exchange refresh_token for access_token and rotate the secret.

    Returns a valid Graph API access_token.
    On TokenExpiredError, sends a reauth alert via Telegram (Phase 3
    handles this with /reauth command) and exits.
    """
    refresh_token = env["TEAMS_REFRESH_TOKEN"]
    gh_pat = os.environ.get("GH_PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "AhmedTyson/TeamsLeech-Bot")

    try:
        access_token, new_refresh_token = exchange_refresh_token(refresh_token)
    except TokenExpiredError as exc:
        log.critical("Refresh token expired: %s", exc)
        # The bot's /reauth handler will guide the user
        raise
    except TokenManagerError as exc:
        log.critical("Token exchange failed: %s", exc)
        raise

    # Rotate the secret if GH_PAT is available
    if gh_pat:
        try:
            rotate_github_secret(new_refresh_token, repo, gh_pat)
            log.info("Refresh token rotated successfully.")
        except Exception as exc:
            log.error("Secret rotation failed (non-fatal): %s", exc)
    else:
        log.warning("GH_PAT not set — skipping secret rotation.")

    return access_token

# ───────────────────────── callback factories ─────────────────────

def _make_on_fetch(access_token: str):
    """Create the on_fetch callback for bot.register_handlers.

    Signature: on_fetch(subject_filter: str | None) → dict
    """
    def on_fetch(subject_filter: str | None = None) -> dict[str, list[dict]]:
        return fetch_recordings(
            access_token=access_token,
            subjects_path=SUBJECTS_PATH,
            state_dir=STATE_DIR,
            subject_filter=subject_filter,
        )
    return on_fetch


def _make_on_upload(access_token: str, tg_client, chat_id: int):
    """Create the on_upload callback for bot.register_handlers.

    bot.py calls on_upload(recordings) synchronously from an async
    handler.  We schedule the async upload_recordings() on the
    running event loop so it executes without blocking.

    Signature: on_upload(recordings: list[dict]) → None
    """
    def on_upload(recordings: list[dict]) -> None:
        asyncio.ensure_future(
            upload_recordings(
                recordings=recordings,
                access_token=access_token,
                tg_client=tg_client,
                chat_id=chat_id,
            )
        )
    return on_upload

# ───────────────────────── main ───────────────────────────────────

def main() -> None:
    """Wire all modules and start the bot."""
    log.info("=" * 50)
    log.info("TeamsLeech Bot — starting up")
    log.info("=" * 50)

    # 1. Validate environment
    env = _validate_env()
    chat_id = int(env["TELEGRAM_CHAT_ID"])

    # 2. Authenticate with Microsoft Graph
    log.info("Step 1/3: Authenticating...")
    try:
        access_token = _authenticate(env)
    except TokenExpiredError:
        # Start bot anyway so user can send /reauth
        log.warning("Starting bot in reauth-only mode.")
        app = create_bot()

        def _fetch_disabled(_=None):
            return {"⚠️ Session Expired": []}

        def _upload_disabled(_=None):
            raise RuntimeError(
                "Uploads disabled — session expired. Send /reauth to recover."
            )

        register_handlers(
            app,
            on_fetch=_fetch_disabled,
            on_upload=_upload_disabled,
            owner_chat_id=chat_id,
        )
        log.info("Bot running in reauth-only mode. Send /reauth in Telegram.")
        app.run()
        return

    log.info("Step 2/3: Creating bot client...")
    app = create_bot()

    # 3. Build callbacks
    on_fetch = _make_on_fetch(access_token)
    on_upload = _make_on_upload(access_token, app, chat_id)

    # 4. Register handlers
    register_handlers(
        app,
        on_fetch=on_fetch,
        on_upload=on_upload,
        owner_chat_id=chat_id,
    )

    # 5. Start polling
    log.info("Step 3/3: Starting bot polling...")
    log.info("Bot is live. Send /check in Telegram.")
    log.info("Press Ctrl+C to stop.")

    async def _run():
        await app.start()
        await send_startup_warnings(app, chat_id)
        from pyrogram import idle
        await idle()
        await app.stop()

    app.run(_run())


if __name__ == "__main__":
    main()
