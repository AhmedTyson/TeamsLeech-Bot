import httpx
import pytest

from teamsleech.services.auth import (
    TokenExchangeError,
    TokenExpiredError,
    TokenManagerError,
    authenticate,
    exchange_refresh_token,
)

TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


class TestExchangeRefreshToken:
    async def test_success(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).respond(
            200,
            json={"access_token": "at_new", "refresh_token": "rt_new"},
        )
        access, refresh = await exchange_refresh_token()
        assert access == "at_new"
        assert refresh == "rt_new"

    async def test_network_error(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).mock(side_effect=httpx.RequestError("DNS failure"))
        with pytest.raises(TokenExchangeError, match="DNS failure"):
            await exchange_refresh_token()

    async def test_expired_token(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).respond(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "Token has expired",
            },
        )
        with pytest.raises(TokenExpiredError, match="Token has expired"):
            await exchange_refresh_token()

    async def test_http_error(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).respond(
            500,
            json={"error": "server_error", "error_description": "Internal"},
        )
        with pytest.raises(TokenExchangeError, match="500"):
            await exchange_refresh_token()

    async def test_missing_tokens_in_response(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).respond(200, json={})
        with pytest.raises(TokenExchangeError, match="missing"):
            await exchange_refresh_token()

    async def test_non_json_error_response(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).respond(400, text="Bad Request")
        with pytest.raises(TokenExchangeError, match="400"):
            await exchange_refresh_token()

    async def test_non_json_success_response(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).respond(200, text="ok")
        with pytest.raises(TokenExchangeError, match="not valid JSON"):
            await exchange_refresh_token()

    async def test_throttled_then_succeeds(self, mock_login_api):
        route = mock_login_api.post(TOKEN_URL)
        route.side_effect = [
            httpx.Response(429, text="throttled"),
            httpx.Response(200, json={"access_token": "at", "refresh_token": "rt"}),
        ]
        access, refresh = await exchange_refresh_token()
        assert (access, refresh) == ("at", "rt")
        assert route.call_count == 2


class TestAuthenticate:
    async def test_no_refresh_token(self, monkeypatch):
        from teamsleech.core.config import settings

        monkeypatch.setattr(settings, "teams_refresh_token", "")
        with pytest.raises(TokenManagerError, match="not set"):
            await authenticate()

    async def test_success(self, mock_login_api, mock_github_api):
        mock_login_api.post(TOKEN_URL).respond(
            200,
            json={"access_token": "at", "refresh_token": "rt"},
        )
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").respond(
            200,
            json={"key": "dGVzdA==", "key_id": "k1"},
        )
        mock_github_api.put("/repos/user/repo/actions/secrets/TEAMS_REFRESH_TOKEN").respond(
            200, text="ok"
        )

        token = await authenticate()
        assert token == "at"

    async def test_secret_rotation_failure_is_nonfatal(self, mock_login_api, mock_github_api):
        mock_login_api.post(TOKEN_URL).respond(
            200,
            json={"access_token": "at", "refresh_token": "rt"},
        )
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").mock(
            side_effect=httpx.RequestError("GitHub down")
        )

        token = await authenticate()
        assert token == "at"

    async def test_secret_rotation_failure_persists_token_locally(
        self, mock_login_api, mock_github_api
    ):
        import os

        from teamsleech.core.config import settings

        mock_login_api.post(TOKEN_URL).respond(
            200,
            json={"access_token": "at", "refresh_token": "rt_new"},
        )
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").mock(
            side_effect=httpx.RequestError("GitHub down")
        )

        token = await authenticate()
        assert token == "at"
        assert settings.teams_refresh_token == "rt_new"
        assert os.environ["TEAMS_REFRESH_TOKEN"] == "rt_new"
