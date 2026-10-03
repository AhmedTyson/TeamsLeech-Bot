from teamsleech.models.domain import Recording
from teamsleech.tg_bot.views import (
    build_checklist_text,
    clean_filename,
    format_date_short,
    format_duration,
    num_label,
    videos_first,
)


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
    assert "Nothing in this scope" in text


def test_build_checklist_text_empty_with_label():
    results = {"Math": []}
    text = build_checklist_text(results, "Last 60 Days")
    assert "Nothing in Last 60 Days" in text
    assert "Math" in text

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


def _rec(name, video, team="T1"):
    return Recording(
        name=name, size_mb=1.0, created="2026-04-01", team_name=team,
        drive_id="d1", item_id=f"i-{name}", subject_name="Math",
        is_video=video,
    )


def test_sections_separate_videos_and_docs():
    text = build_checklist_text(
        {"Math": [_rec("b.pdf", False), _rec("a.mp4", True)]}, "All"
    )
    vid_pos = text.index("🎬 **Recordings**")
    doc_pos = text.index("📄 **Documents**")
    assert vid_pos < doc_pos
    assert text.index("a.mp4") < text.index("b.pdf")


def test_video_only_notes_no_documents():
    text = build_checklist_text({"Math": [_rec("a.mp4", True)]}, "All")
    assert "No documents found" in text
    assert "📄 **Documents**" not in text


def test_doc_only_notes_no_recordings():
    text = build_checklist_text({"Math": [_rec("b.pdf", False)]}, "All")
    assert "No recordings found" in text


def test_videos_first_ordering():
    recs = [_rec("b.pdf", False), _rec("a.mp4", True), _rec("c.mp4", True)]
    assert [r.name for r in videos_first(recs)] == ["a.mp4", "c.mp4", "b.pdf"]
