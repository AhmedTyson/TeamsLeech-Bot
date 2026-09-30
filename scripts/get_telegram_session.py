"""Mint a Telegram user session string for large (>50 MB) uploads.

Bot tokens are capped at 50 MB by the Bot API; a user session (MTProto)
uploads up to 2 GB. Run LOCALLY (never in CI), then store the printed
string as the TELEGRAM_SESSION_STRING GitHub Secret and delete any file
copy. Treat the string like a password.

Usage
-----
    python scripts/get_telegram_session.py
"""

import os


def main() -> None:
    from pyrogram import Client

    api_id = int(os.environ.get("TELEGRAM_API_ID", "0") or 0)
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    if not api_id or not api_hash:
        msg = "Set TELEGRAM_API_ID and TELEGRAM_API_HASH env vars first."
        raise SystemExit(msg)

    with Client(
        name="teamsleech_session_maker",
        api_id=api_id,
        api_hash=api_hash,
        in_memory=True,
    ) as app:
        session_string = app.export_session_string()

    print("\nYour session string (store as TELEGRAM_SESSION_STRING secret):\n")
    print(session_string)


if __name__ == "__main__":
    main()
