"""
Phase 5 — Manual verification script for main.py (orchestrator).

This script validates that main.py correctly wires all modules and
starts the bot with real callbacks.

Prerequisites
-------------
1.  pip install requests pyrogram tgcrypto python-dotenv pynacl
2.  .env must contain ALL required env vars:
        TEAMS_REFRESH_TOKEN=...
        TELEGRAM_API_ID=...
        TELEGRAM_API_HASH=...
        TELEGRAM_BOT_TOKEN=...
        TELEGRAM_SESSION=...
        TELEGRAM_CHAT_ID=...
    Optional (for secret rotation):
        GH_PAT=...
        GITHUB_REPOSITORY=AhmedTyson/TeamsLeech-Bot
3.  Run:  python tests/test_main.py
4.  Open Telegram → interact with the bot.
5.  Press Ctrl+C to stop.

Test Checklist
--------------
1. Script starts without errors → env validation passes
2. Access token acquired → auth step succeeds
3. Bot comes online → /start shows welcome message
4. /check → subject buttons → tap subject → REAL recordings appear
5. Select recordings → tap Upload Selected → real download + upload
6. Verify uploaded file in Telegram Saved Messages
7. /reauth → recovery guide appears
8. Ctrl+C → bot shuts down cleanly
"""

import os
import sys

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()


def main() -> None:
    print()
    print("=" * 60)
    print("  Phase 5 — main.py (orchestrator) verification")
    print("=" * 60)
    print()
    print("  This runs main.py with your real .env credentials.")
    print("  The bot will go live — interact with it in Telegram.")
    print("  Press Ctrl+C to stop.")
    print()
    print("  Test checklist:")
    print("  1. No startup errors (env validation passes)")
    print("  2. Access token acquired (auth step succeeds)")
    print("  3. /start → welcome message")
    print("  4. /check → subject buttons → tap → REAL recordings")
    print("  5. Select + Upload Selected → real download + upload")
    print("  6. Verify file in Telegram Saved Messages")
    print("  7. /reauth → recovery guide")
    print("  8. Ctrl+C → clean shutdown")
    print()

    # Import and run main
    from main import main as run_main
    run_main()


if __name__ == "__main__":
    main()
