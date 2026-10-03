from unittest.mock import AsyncMock, patch

import pytest
import respx

from teamsleech.services.subjects_store import (
    load_subjects_text,
    parse_gist_ref,
    save_subjects_text_async,
)

RAW = "https://gist.githubusercontent.com/u/abc123/raw/subjects.json"


class TestParseGistRef:
    def test_valid(self):
        assert parse_gist_ref(RAW) == ("abc123", "subjects.json")

    def test_with_revision(self):
        url = "https://gist.githubusercontent.com/u/abc123/raw/rev1/subjects.json"
        assert parse_gist_ref(url) == ("abc123", "subjects.json")

    def test_invalid(self):
        with pytest.raises(ValueError, match="raw gist file URL"):
            parse_gist_ref("https://example.com/x.json")
        with pytest.raises(ValueError, match="raw gist file URL"):
            parse_gist_ref("")


class TestLoad:
    def test_falls_back_to_secret(self, monkeypatch):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "subjects_url", "")
        monkeypatch.setattr(settings, "subjects_json", '{"subjects": []}')
        assert load_subjects_text() == '{"subjects": []}'

    def test_fetches_gist_when_url_set(self, monkeypatch):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "subjects_url", RAW)
        with respx.mock(base_url="https://gist.githubusercontent.com") as mock:
            mock.get("/u/abc123/raw/subjects.json").respond(
                200, text='{"subjects": []}'
            )
            assert load_subjects_text() == '{"subjects": []}'


class TestSave:
    async def test_saves_to_gist(self, monkeypatch, mock_github_api):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "subjects_url", RAW)
        monkeypatch.setattr(settings, "gh_pat", "ghp_test")
        route = mock_github_api.patch("/gists/abc123").respond(200, json={})
        assert await save_subjects_text_async('{"a": 1}') == "gist"
        assert route.called

    async def test_gist_denied_helpful_message(self, monkeypatch, mock_github_api):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "subjects_url", RAW)
        monkeypatch.setattr(settings, "gh_pat", "ghp_test")
        mock_github_api.patch("/gists/abc123").respond(403, json={})
        with pytest.raises(ValueError, match="gist.*scope"):
            await save_subjects_text_async('{"a": 1}')

    async def test_falls_back_to_secret(self, monkeypatch):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "subjects_url", "")
        with patch(
            "teamsleech.services.github_secrets.rotate_github_secret",
            AsyncMock(),
        ):
            assert await save_subjects_text_async('{"a": 1}') == "secret"
