import os

os.environ.setdefault("TEAMS_REFRESH_TOKEN", "test_rt")
os.environ.setdefault("TELEGRAM_API_ID", "12345")
os.environ.setdefault("TELEGRAM_API_HASH", "test_hash")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_bot")
os.environ.setdefault("TELEGRAM_CHAT_ID", "67890")
os.environ.setdefault("GH_PAT", "ghp_test")
os.environ.setdefault("GITHUB_REPOSITORY", "user/repo")

from unittest.mock import AsyncMock

import pytest
import respx

from teamsleech.core.constants import GRAPH_BASE_URL


@pytest.fixture
def mock_graph_api():
    with respx.mock(base_url=GRAPH_BASE_URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def mock_github_api():
    with respx.mock(base_url="https://api.github.com", assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def mock_login_api():
    with respx.mock(base_url="https://login.microsoftonline.com", assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def graph_client():
    from teamsleech.services.graph import GraphClient
    return GraphClient(access_token="fake_token")


@pytest.fixture
def mock_pyrogram_client():
    client = AsyncMock()
    client.get_chat = AsyncMock()
    client.send_document = AsyncMock()
    client.download_media = AsyncMock()
    client.delete_messages = AsyncMock()
    return client


@pytest.fixture
def sample_recording():
    from teamsleech.models.domain import Recording
    return Recording(
        name="lecture.mp4",
        size_mb=100.0,
        created="2024-01-15",
        time="10:30",
        duration_ms=1_800_000,
        drive_id="drive123",
        item_id="item456",
        team_name="CS-A",
        subject_name="Math",
        is_video=True,
    )


@pytest.fixture
def sample_pdf_recording():
    from teamsleech.models.domain import Recording
    return Recording(
        name="notes.pdf",
        size_mb=5.0,
        created="2024-01-15",
        time="10:30",
        duration_ms=0,
        drive_id="drive123",
        item_id="item789",
        team_name="CS-A",
        subject_name="Math",
        is_video=False,
    )


@pytest.fixture
def sample_subject():
    from teamsleech.models.domain import SubjectConfig
    return SubjectConfig(name="Math", short="MTH", keywords=["math", "algebra"])


@pytest.fixture
def sample_team():
    from teamsleech.models.domain import Team
    return Team(id="team1", display_name="CS-A 2024")



@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    from teamsleech.core.config import settings
    monkeypatch.setattr(settings, "gh_pat", "ghp_test")
    monkeypatch.setattr(settings, "github_repository", "user/repo")
    monkeypatch.setattr(settings, "teams_refresh_token", "test_rt")
    monkeypatch.setattr(settings, "teams_client_id", "test_client_id")
    monkeypatch.setattr(settings, "subjects_json", "")
    monkeypatch.setattr(settings, "subjects_path", "/dev/null/subjects.json")
