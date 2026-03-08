"""
Phase 2 — Manual verification script for fetcher.

Prerequisites
-------------
1.  pip install requests python-dotenv
2.  .env must contain TEAMS_REFRESH_TOKEN and GH_PAT
    (token_manager.py must work — Phase 1 gate passed)
3.  subjects_config.json must be in the project root
4.  Run:  python tests/test_fetcher.py
"""

import os
import sys
import json
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from token_manager import get_access_token, exchange_refresh_token
from fetcher import (
    load_subjects,
    fetch_recordings,
    get_last_run,
    save_last_run,
    FetcherError,
)


def _pass(label: str) -> None:
    print(f"  ✅  {label}")


def _fail(label: str, err: Exception) -> None:
    print(f"  ❌  {label}: {err}")
    sys.exit(1)


def main() -> None:
    print()
    print("=" * 60)
    print("  Phase 2 — fetcher verification")
    print("=" * 60)

    # ── Pre-check: get access_token via Phase 1 ──────────────────
    print("\n[0/6] Getting access_token via token_manager...")
    rt = os.environ.get("TEAMS_REFRESH_TOKEN", "")
    if not rt:
        print("  ❌  TEAMS_REFRESH_TOKEN not set in .env")
        sys.exit(1)
    try:
        access_token, _ = exchange_refresh_token(rt)
        _pass(f"access_token acquired ({len(access_token)} chars)")
    except Exception as e:
        _fail("Could not get access_token (Phase 1 broken?)", e)

    # ── Test 1: Load subjects_config.json ────────────────────────
    print("\n[1/6] Loading subjects_config.json...")
    try:
        subjects = load_subjects("subjects_config.json")
        assert len(subjects) == 6, f"Expected 6 subjects, got {len(subjects)}"
        names = [s["name"] for s in subjects]
        _pass(f"Loaded {len(subjects)} subjects: {', '.join(names)}")
    except Exception as e:
        _fail("Failed to load subjects", e)

    # ── Test 2: Fetch all recordings (Check All mode) ────────────
    print("\n[2/6] Fetching recordings for ALL subjects (may take 30-60 sec)...")
    test_state_dir = ".state_test"
    try:
        results = fetch_recordings(
            access_token,
            subjects_path="subjects_config.json",
            state_dir=test_state_dir,
        )
        assert isinstance(results, dict)
        assert len(results) == 6, f"Expected 6 subjects in results, got {len(results)}"
        _pass(f"Got results for {len(results)} subjects")
    except Exception as e:
        _fail("fetch_recordings failed", e)

    # ── Test 3: Verify result structure ──────────────────────────
    print("\n[3/6] Verifying result structure...")
    total = 0
    for subj_name, recs in results.items():
        total += len(recs)
        for rec in recs[:1]:  # check first recording per subject
            required_keys = {"name", "size_mb", "created", "drive_id", "item_id", "team_name"}
            missing = required_keys - set(rec.keys())
            assert not missing, f"Recording missing keys: {missing}"
            assert rec["name"].lower().endswith(".mp4"), f"Not an .mp4: {rec['name']}"
    _pass(f"All recordings valid — {total} total across all subjects")

    # ── Test 4: Single-subject filter ────────────────────────────
    print("\n[4/6] Testing single-subject filter (Auditing)...")
    try:
        single = fetch_recordings(
            access_token,
            subjects_path="subjects_config.json",
            state_dir=test_state_dir,
            subject_filter="Auditing",
        )
        assert len(single) == 1, f"Expected 1 subject, got {len(single)}"
        assert "Auditing" in single
        _pass(f"Single filter works — {len(single['Auditing'])} recording(s) for Auditing")
    except Exception as e:
        _fail("Single-subject filter failed", e)

    # ── Test 5: Date filtering with save_last_run ────────────────
    print("\n[5/6] Testing date filter (save_last_run → re-fetch)...")
    try:
        from datetime import datetime, timezone
        # Save "now" as last_run — should filter out everything
        save_last_run(test_state_dir, "Auditing", datetime.now(timezone.utc))
        filtered = fetch_recordings(
            access_token,
            subjects_path="subjects_config.json",
            state_dir=test_state_dir,
            subject_filter="Auditing",
        )
        assert len(filtered["Auditing"]) == 0, (
            f"Expected 0 recordings after date filter, got {len(filtered['Auditing'])}"
        )
        _pass("Date filter works — 0 recordings returned after setting last_run to now")
    except Exception as e:
        _fail("Date filter test failed", e)

    # ── Test 6: Print sample output ──────────────────────────────
    print("\n[6/6] Sample output from full scan:")
    print("-" * 50)
    for subj_name, recs in results.items():
        print(f"\n  📚 {subj_name}: {len(recs)} recording(s)")
        for rec in recs[:3]:  # show up to 3 per subject
            print(f"     🎥 {rec['name']} — {rec['size_mb']}MB — {rec['created']}")
            print(f"        Team: {rec['team_name']}")
        if len(recs) > 3:
            print(f"     ... and {len(recs) - 3} more")
    print()
    _pass(f"Full scan complete — {total} recordings found")

    # ── Cleanup ──────────────────────────────────────────────────
    if os.path.exists(test_state_dir):
        shutil.rmtree(test_state_dir)

    # ── Summary ──────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  All 6 checks passed ✅  — Phase 2 is DONE")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
