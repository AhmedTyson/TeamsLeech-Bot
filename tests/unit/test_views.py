import pytest
from teamsleech.tg_bot.views import (
    num_label,
    clean_filename,
    format_date_short,
    format_duration,
    build_checklist_text,
)
from teamsleech.models.domain import Recording

def test_num_label():
    assert num_label(1) == "1."
    assert num_label(10) == "10."

def test_clean_filename():
    assert clean_filename("Math-Meeting Recording") == "Math"
    assert clean_filename("Class-20260101_120000") == "Class"

def test_format_date_short():
    assert format_date_short("2026-04-01") == "Apr 01"
    assert format_date_short("invalid-date") == "invalid-date"

def test_format_duration():
    assert format_duration(0) == ""
    assert format_duration(5000) == "5s"
    assert format_duration(65000) == "1m 05s"
    assert format_duration(3665000) == "1h 1m"
    assert format_duration("invalid") == ""

def test_build_checklist_text_empty():
    results = {}
    text = build_checklist_text(results)
    assert "No new files found" in text

def test_build_checklist_text_with_data():
    recs = [
        Recording(
            id="1", name="Vid1", url="http", 
            is_video=True, size_mb=10.0, 
            created="2026-04-01", team_name="T1",
            duration_ms=60000,
            drive_id="d1", item_id="i1", subject_name="Math"
        )
    ]
    results = {"Math": recs}
    text = build_checklist_text(results, scan_label="Today")
    assert "Scan Results" in text
    assert "Today" in text
    assert "Vid1" in text
    assert "10.0 MB" in text
    assert "1m 00s" in text
