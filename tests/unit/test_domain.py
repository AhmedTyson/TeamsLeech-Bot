import pytest
from pydantic import ValidationError
from teamsleech.models.domain import SubjectConfig, Recording, Team, UserSession

def test_subject_config_defaults():
    s = SubjectConfig(name="Math", short="MTH", keywords=["math", "algebra"])
    assert s.name == "Math"
    assert s.short == "MTH"
    assert s.doctor == ""
    assert s.keywords == ["math", "algebra"]

def test_subject_config_minimal():
    s = SubjectConfig(name="Physics")
    assert s.name == "Physics"
    assert s.short == ""
    assert s.doctor == ""
    assert s.keywords == []

def test_subject_config_invalid():
    with pytest.raises(ValidationError):
        SubjectConfig()

def test_recording_defaults():
    r = Recording(
        name="lecture.mp4",
        size_mb=100.0,
        created="2024-01-15",
        time="10:30",
        duration_ms=1800000,
        drive_id="drive123",
        item_id="item456",
        team_name="CS-A",
        subject_name="Math",
    )
    assert r.name == "lecture.mp4"
    assert r.is_video is True
    assert r.size_mb == 100.0

def test_recording_non_video():
    r = Recording(
        name="notes.pdf",
        size_mb=5.0,
        created="2024-01-15",
        drive_id="d1",
        item_id="i1",
        team_name="CS-A",
        subject_name="Math",
    )
    assert r.is_video is False
    assert r.time == ""

def test_team_model():
    t = Team(id="team1", display_name="CS-A 2024")
    assert t.id == "team1"
    assert t.display_name == "CS-A 2024"

def test_team_populate_by_name():
    t = Team.model_validate({"id": "t1", "displayName": "Math 101"})
    assert t.display_name == "Math 101"

def test_user_session_defaults():
    session = UserSession()
    assert session.is_searching_teams is False
    assert session.pending_add_step == ""
    assert session.pending_add_team is None
    assert session.pending_add_data == {}
    assert session.pending_rename_idx is None
    assert session.pending_suggestion is None
    assert session.date_input_pending is False
    assert session.subject_filter is None
    assert session.pending_recordings == []
    assert session.selected_indices == set()
    assert session.rename_overrides == {}
    assert session.scan_label == ""
