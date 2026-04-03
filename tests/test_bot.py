"""
Phase 3 — Manual verification script for bot.py.

This script starts the bot in live mode so you can interact with it
via Telegram. It wires up a MOCK fetcher that returns fake recordings
(no real Graph API calls needed) so you can test the full UI flow.

Prerequisites
-------------
1.  pip install pyrogram tgcrypto python-dotenv
2.  .env must contain:
        TELEGRAM_API_ID=...
        TELEGRAM_API_HASH=...
        TELEGRAM_BOT_TOKEN=...
        TELEGRAM_SESSION=...   (from scripts/generate_session.py)
        TELEGRAM_CHAT_ID=...
3.  Run:  python tests/test_bot.py
4.  Open Telegram → find your bot → run through the checklist below.
5.  Press Ctrl+C in this terminal to stop the bot.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from bot import create_bot, register_handlers


# ── Mock fetcher: returns fake recordings, no Graph API needed ───

MOCK_RESULTS_SINGLE = {
    "Auditing": [
        {
            "name": "Lecture_01_Intro_to_Auditing.mp4",
            "size_mb": 245.3,
            "created": "2026-03-01",
            "drive_id": "mock_drive_001",
            "item_id": "mock_item_001",
            "team_name": "Auditing Section A",
        },
        {
            "name": "Lecture_02_Internal_Controls.mp4",
            "size_mb": 312.8,
            "created": "2026-03-03",
            "drive_id": "mock_drive_001",
            "item_id": "mock_item_002",
            "team_name": "Auditing Section A",
        },
    ],
}

MOCK_RESULTS_ALL = {
    "Advanced Database": [
        {
            "name": "AdvDB_Lecture_05_Normalization.mp4",
            "size_mb": 198.4,
            "created": "2026-03-02",
            "drive_id": "mock_drive_010",
            "item_id": "mock_item_010",
            "team_name": "Advanced DB Group 1",
        },
    ],
    "Auditing": MOCK_RESULTS_SINGLE["Auditing"],
    "Economics of Information": [],
    "Internet Applications": [
        {
            "name": "WebDev_Lab3_REST_APIs.mp4",
            "size_mb": 156.1,
            "created": "2026-03-04",
            "drive_id": "mock_drive_020",
            "item_id": "mock_item_020",
            "team_name": "Internet Apps 2026",
        },
    ],
    "Management Information Systems": [],
    "Operations Research": [
        {
            "name": "OR_Lecture_07_Linear_Programming.mp4",
            "size_mb": 402.9,
            "created": "2026-03-05",
            "drive_id": "mock_drive_030",
            "item_id": "mock_item_030",
            "team_name": "O.R. Spring 2026",
        },
    ],
}

MOCK_RESULTS_EMPTY = {"Auditing": []}


async def mock_fetch(subject_filter: str | None = None, date_start: str | None = None, date_end: str | None = None) -> dict:
    """Mock fetcher that returns canned data (async to match new API)."""
    date_info = f"start={date_start}, end={date_end}"
    if subject_filter is None:
        print(f"  [mock] on_fetch(Check All, {date_info}) → {sum(len(v) for v in MOCK_RESULTS_ALL.values())} recordings")
        return MOCK_RESULTS_ALL
    if subject_filter in MOCK_RESULTS_SINGLE:
        print(f"  [mock] on_fetch('{subject_filter}', {date_info}) → {len(MOCK_RESULTS_SINGLE[subject_filter])} recordings")
        return {subject_filter: MOCK_RESULTS_SINGLE[subject_filter]}
    # Subjects with no recordings
    print(f"  [mock] on_fetch('{subject_filter}', {date_info}) → 0 recordings")
    return {subject_filter: []}


async def mock_upload(recordings: list[dict], progress_cb) -> None:
    """Mock uploader that just prints what would be uploaded and simulates progress."""
    print(f"\n  [mock] on_upload called with {len(recordings)} recording(s):")
    total_mb = sum(r.get("size_mb", 0) for r in recordings)
    await progress_cb("start", {"total": len(recordings), "total_mb": total_mb})
    for i, rec in enumerate(recordings):
        name = rec['name']
        print(f"    📤 {name} — {rec['size_mb']}MB — {rec['created']}")
        print(f"     Team: {rec['team_name']}")
        await progress_cb("file_progress", {"index": i, "name": name, "percent": 50, "speed_mbps": 1.2})
        await progress_cb("file_done", {"index": i, "name": name, "size_mb": rec['size_mb'], "elapsed_s": 2.5})
    await progress_cb("all_done", {"total": len(recordings), "total_mb": total_mb, "elapsed_s": 5.0})
    print()


def main() -> None:
    print()
    print("=" * 60)
    print("  Phase 3 — bot.py live test (mock fetcher)")
    print("=" * 60)
    print()
    print("  The bot is starting. Open Telegram and interact with it.")
    print("  Press Ctrl+C to stop.")
    print()
    print("  Test checklist:")
    print("  1. Send /start  → should show welcome message")
    print("  2. Send /check  → should show 6 subject buttons + Check All")
    print("  3. Tap a subject button → should show mock recordings")
    print("  4. Toggle checkboxes → marks should update (☐ → ☑)")
    print("  5. Tap Upload Selected → should print selected recordings")
    print("  6. Send /check → tap Check All → should show all subjects")
    print("  7. Type 'Auditing' as text → should trigger scan")
    print("  8. Send /reauth → should show 4-step recovery guide")
    print()

    app = create_bot()
    register_handlers(app, on_fetch=mock_fetch, on_upload=mock_upload)

    print("  Bot registered. Starting polling...")
    print()
    app.run()


if __name__ == "__main__":
    main()
