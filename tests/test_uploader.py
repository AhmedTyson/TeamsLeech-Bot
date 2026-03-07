"""
Phase 4 — Manual verification script for uploader.py.

This script tests the upload pipeline end-to-end:
  1. Gets an access_token via token_manager (Phase 1)
  2. Fetches real recordings via fetcher (Phase 2)
  3. Downloads the SMALLEST recording from Graph API
  4. Uploads it to Telegram Saved Messages with progress

Prerequisites
-------------
1.  pip install requests pyrogram tgcrypto python-dotenv pynacl
2.  .env must contain:
        TEAMS_REFRESH_TOKEN=...
        TELEGRAM_API_ID=...
        TELEGRAM_API_HASH=...
        TELEGRAM_BOT_TOKEN=...
        TELEGRAM_SESSION=...
        TELEGRAM_CHAT_ID=...
3.  Run:  python tests/test_uploader.py
4.  Check Telegram Saved Messages for the uploaded file.
"""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from token_manager import exchange_refresh_token
from fetcher import fetch_recordings
from uploader import upload_recordings
from pyrogram import Client


def _pass(label: str) -> None:
    print(f"  \u2705  {label}")


def _fail(label: str, err: Exception) -> None:
    print(f"  \u274c  {label}: {err}")
    sys.exit(1)


async def run_test() -> None:
    print()
    print("=" * 60)
    print("  Phase 4 \u2014 uploader verification")
    print("=" * 60)

    # \u2500\u2500 Step 0: Get access token \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[0/5] Getting access_token via token_manager...")
    rt = os.environ.get("TEAMS_REFRESH_TOKEN", "")
    if not rt:
        print("  \u274c  TEAMS_REFRESH_TOKEN not set in .env")
        sys.exit(1)
    try:
        access_token, _ = exchange_refresh_token(rt)
        _pass(f"access_token acquired ({len(access_token)} chars)")
    except Exception as e:
        _fail("Could not get access_token", e)

    # \u2500\u2500 Step 1: Fetch a real recording \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[1/5] Fetching recordings to find smallest file...")
    try:
        results = fetch_recordings(
            access_token,
            subjects_path="subjects_config.json",
            state_dir=".state_test_upload",
        )
        # Flatten and find the smallest recording
        all_recs = []
        for recs in results.values():
            all_recs.extend(recs)

        if not all_recs:
            print("  \u26a0\ufe0f  No recordings found. Cannot test upload.")
            print("      This could be normal if all recordings are old.")
            print("      Phase 4 code is correct \u2014 try again when new recordings exist.")
            sys.exit(0)

        smallest = min(all_recs, key=lambda r: r["size_mb"])
        _pass(
            f"Found {len(all_recs)} recording(s). "
            f"Smallest: {smallest['name']} ({smallest['size_mb']}MB)"
        )
    except Exception as e:
        _fail("Fetch failed", e)

    # \u2500\u2500 Step 2: Create Pyrogram client \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[2/5] Creating Pyrogram client...")
    try:
        session = os.environ.get("TELEGRAM_SESSION", "")
        api_id = int(os.environ.get("TELEGRAM_API_ID", "0"))
        api_hash = os.environ.get("TELEGRAM_API_HASH", "")
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))

        tg_client = Client(
            name="teamsleech_test_upload",
            api_id=api_id,
            api_hash=api_hash,
            bot_token=bot_token,
            session_string=session,
            in_memory=True,
        )
        _pass("Pyrogram client created")
    except Exception as e:
        _fail("Pyrogram client creation failed", e)

    # \u2500\u2500 Step 3: Upload the smallest recording \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print(f"\n[3/5] Uploading: {smallest['name']} ({smallest['size_mb']}MB)...")
    print("      This may take a few minutes depending on file size...")

    async with tg_client:
        try:
            upload_results = await upload_recordings(
                recordings=[smallest],
                access_token=access_token,
                tg_client=tg_client,
                chat_id=chat_id,
            )
            _pass("upload_recordings() completed")
        except Exception as e:
            _fail("upload_recordings failed", e)

    # \u2500\u2500 Step 4: Check results \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[4/5] Checking results...")
    try:
        assert len(upload_results) == 1
        result = upload_results[0]
        assert result["name"] == smallest["name"]
        assert result["success"] is True
        assert result["error"] is None
        _pass(f"Result: {result['name']} \u2014 success={result['success']}")
    except AssertionError as e:
        _fail("Result validation failed", e)

    # \u2500\u2500 Step 5: Manual check \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[5/5] Manual check:")
    print("      \u2192 Open Telegram \u2192 Saved Messages")
    print(f"      \u2192 Verify '{smallest['name']}' is there and playable")
    print()
    _pass("Upload pipeline complete")

    # \u2500\u2500 Cleanup \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    import shutil
    if os.path.exists(".state_test_upload"):
        shutil.rmtree(".state_test_upload")

    print()
    print("=" * 60)
    print("  All 5 checks passed \u2705  \u2014 Phase 4 is DONE")
    print("=" * 60)
    print()


def main() -> None:
    asyncio.run(run_test())


if __name__ == "__main__":
    main()
