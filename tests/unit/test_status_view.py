"""Tests for the /status text builder."""

from teamsleech.models.domain import SubjectConfig
from teamsleech.tg_bot.views import build_status_text

SUBJECTS = [
    SubjectConfig(
        name="Fabrication Tech", short="FT", topic_id=123, next_no=4
    ),
    SubjectConfig(name="Math", short="MTH", kind="section", next_no=1),
]


def test_status_ok():
    text = build_status_text(True, "session OK", SUBJECTS, 2, 12.0, 43.0)
    assert "✅" in text
    assert "session OK" in text
    assert "`123`" in text
    assert "not linked" in text
    assert "L04" in text
    assert "Sec01" in text
    assert "2 failed download(s)" in text
    assert "Browser Login" not in text


def test_status_expired_nags_browser_login():
    text = build_status_text(
        False, "session expired (HTTP 401)", SUBJECTS, 0, 1.0, 54.0
    )
    assert "⚠️" in text
    assert "expired" in text
    assert "🖥 **Browser Login**" in text


def test_status_no_subjects():
    text = build_status_text(True, "session OK", [], 0, 0.0, 55.0)
    assert "no subjects configured" in text
