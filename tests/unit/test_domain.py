import pytest
from pydantic import ValidationError
from teamsleech.models.domain import SubjectConfig, Recording, Team, UserSession

def test_subject_config_defaults():
    config = SubjectConfig(name="Database Systems")
    assert config.name == "Database Systems"
    assert config.short == ""
    assert config.doctor == ""
    assert config.keywords == []

def test_subject_config_populated():
    config = SubjectConfig(
        name="Database Systems",
        short="DB",
        doctor="Dr. Smith",
        keywords=["database", "sql"]
    )
    assert config.short == "DB"
    assert config.keywords == ["database", "sql"]

def test_recording_validation():
    # Missing required fields should raise ValidationError
    with pytest.raises(ValidationError):
        Recording(name="test.mp4")
        
    rec = Recording(
        name="Lec1.mp4",
        size_mb=150.5,
        created="2026-04-01",
        drive_id="d1",
        item_id="i1",
        team_name="CS101",
        subject_name="Computer Science"
    )
    assert rec.is_video is True  # Default value
    assert rec.duration_ms == 0

def test_team_alias():
    # Should accept displayName due to alias and populate_by_name
    team1 = Team(id="t1", displayName="Test Team")
    assert team1.display_name == "Test Team"
    
    team2 = Team(id="t2", display_name="Test Team 2")
    assert team2.display_name == "Test Team 2"

def test_user_session_defaults():
    session = UserSession()
    assert session.is_searching_teams is False
    assert session.pending_recordings == []
    assert session.selected_indices == set()
    assert session.rename_overrides == {}
