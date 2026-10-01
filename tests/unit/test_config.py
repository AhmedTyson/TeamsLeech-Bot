import pytest
from pydantic import ValidationError

from teamsleech.core.config import AppConfig


def _env():
    return {
        "TEAMS_REFRESH_TOKEN": "rt",
        "TELEGRAM_API_ID": "123",
        "TELEGRAM_API_HASH": "hash",
        "TELEGRAM_BOT_TOKEN": "tok",
        "TELEGRAM_CHAT_ID": "456",
        "GH_PAT": "",
    }


def test_builds_from_env(monkeypatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    cfg = AppConfig()
    assert cfg.telegram_api_id == 123
    assert cfg.telegram_chat_id == 456
    assert cfg.gh_pat == ""
    assert cfg.teams_client_id.startswith("04b07795")


def test_missing_required_raises(monkeypatch):
    for k in _env():
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        AppConfig()


def test_empty_client_id_falls_back_to_default(monkeypatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("TEAMS_CLIENT_ID", "")
    assert AppConfig().teams_client_id.startswith("04b07795")
