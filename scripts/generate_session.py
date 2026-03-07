"""
One-time script — Generate a Pyrogram session string.

Run this ONCE locally, then save the output string as
TELEGRAM_SESSION in GitHub Secrets.

Usage
-----
1. Create/update .env with:
       TELEGRAM_API_ID=<from my.telegram.org>
       TELEGRAM_API_HASH=<from my.telegram.org>

2. Run:
       python scripts/generate_session.py

3. Follow the prompts (phone number, login code).

4. Copy the printed session string → GitHub repo → Settings →
   Secrets → New secret → Name: TELEGRAM_SESSION → Paste → Save.

5. You will never need to run this again unless your Telegram
   session is revoked.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from pyrogram import Client


def main() -> None:
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        print("❌  Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env first.")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  Pyrogram Session String Generator")
    print("=" * 60)
    print()
    print("  You will be asked for your phone number and a login code.")
    print("  This only needs to be done ONCE.")
    print()

    app = Client(
        "teamsleech_session",
        api_id=int(api_id),
        api_hash=api_hash,
        in_memory=True,  # don't write session file to disk
    )

    with app:
        session_string = app.export_session_string()

    print()
    print("=" * 60)
    print("  ✅  Session string generated!")
    print("=" * 60)
    print()
    print("  Copy the ENTIRE string below (it's one long line):")
    print()
    print(session_string)
    print()
    print("  Save it as TELEGRAM_SESSION in GitHub Secrets.")
    print("=" * 60)


if __name__ == "__main__":
    main()
