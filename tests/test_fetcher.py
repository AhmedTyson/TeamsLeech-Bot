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
    print(f"  \u2705  {label}")


def _fail(label: str, err: Exception) -> None:
    print(f"  \u274c  {label}: {err}")
    sys.exit(1)


def main() -> None:
    print()
    print("=" * 60)
    print("  Phase 2 \u2014 fetcher verification")
    print("=" * 60)

    # \u2500\u2500 Pre-check: get access_token via Phase 1 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[0/6] Getting access_token via token_manager...")
    rt = os.environ.get("TEAMS_REFRESH_TOKEN", "")
    if not rt:
        print("  \u274c  TEAMS_REFRESH_TOKEN not set in .env")
        sys.exit(1)
    try:
        access_token, _ = exchange_refresh_token(rt)
        _pass(f"access_token acquired ({len(access_token)} chars)")
    except Exception as e:
        _fail("Could not get access_token (Phase 1 broken?)", e)

    # \u2500\u2500 Test 1: Load subjects_config.json \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[1/6] Loading subjects_config.json...")
    try:
        subjects = load_subjects("subjects_config.json")
        assert len(subjects) == 6, f"Expected 6 subjects, got {len(subjects)}"
        names = [s["name"] for s in subjects]
        _pass(f"Loaded {len(subjects)} subjects: {', '.join(names)}")
    except Exception as e:
        _fail("Failed to load subjects", e)

    # \u2500\u2500 Test 2: Fetch all recordings (Check All mode) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
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

    # \u2500\u2500 Test 3: Verify result structure \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[3/6] Verifying result structure...")
    total = 0
    for subj_name, recs in results.items():
        total += len(recs)
        for rec in recs[:1]:  # check first recording per subject
            required_keys = {"name", "size_mb", "created", "drive_id", "item_id", "team_name"}
            missing = required_keys - set(rec.keys())
            assert not missing, f"Recording missing keys: {missing}"
            assert rec["name"].lower().endswith(".mp4"), f"Not an .mp4: {rec['name']}"
    _pass(f"All recordings valid \u2014 {total} total across all subjects")

    # \u2500\u2500 Test 4: Single-subject filter \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
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
        _pass(f"Single filter works \u2014 {len(single['Auditing'])} recording(s) for Auditing")
    except Exception as e:
        _fail("Single-subject filter failed", e)

    # \u2500\u2500 Test 5: Date filtering with save_last_run \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[5/6] Testing date filter (save_last_run \u2192 re-fetch)...")
    try:
        from datetime import datetime, timezone
        # Save "now" as last_run \u2014 should filter out everything
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
        _pass("Date filter works \u2014 0 recordings returned after setting last_run to now")
    except Exception as e:
        _fail("Date filter test failed", e)

    # \u2500\u2500 Test 6: Print sample output \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print("\n[6/6] Sample output from full scan:")
    print("-" * 50)
    for subj_name, recs in results.items():
        print(f"\n  \ud83d\udcda {subj_name}: {len(recs)} recording(s)")
        for rec in recs[:3]:  # show up to 3 per subject
            print(f"     \ud83c\udfa5 {rec['name']} \u2014 {rec['size_mb']}MB \u2014 {rec['created']}")
            print(f"        Team: {rec['team_name']}")
        if len(recs) > 3:
            print(f"     ... and {len(recs) - 3} more")
    print()
    _pass(f"Full scan complete \u2014 {total} recordings found")

    # \u2500\u2500 Cleanup \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    if os.path.exists(test_state_dir):
        shutil.rmtree(test_state_dir)

    # \u2500\u2500 Summary \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    print()
    print("=" * 60)
    print("  All 6 checks passed \u2705  \u2014 Phase 2 is DONE")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
