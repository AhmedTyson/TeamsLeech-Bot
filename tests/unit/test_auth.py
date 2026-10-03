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
        mock_login_api.post(TOKEN_URL).mock(
            side_effect=httpx.RequestError("DNS failure")
        )
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

    async def test_custom_client_id_in_payload(self, mock_login_api, monkeypatch):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "teams_client_id", "my-app-id")
        route = mock_login_api.post(TOKEN_URL).respond(
            200, json={"access_token": "at", "refresh_token": "rt"}
        )
        await exchange_refresh_token()
        assert "my-app-id" in route.calls[0].request.content.decode()

    async def test_empty_client_id_falls_back_to_default(
        self, mock_login_api, monkeypatch
    ):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "teams_client_id", "")
        route = mock_login_api.post(TOKEN_URL).respond(
            200, json={"access_token": "at", "refresh_token": "rt"}
        )
        await exchange_refresh_token()
        assert "04b07795-8ddb-461a-bbee-02f9e1bf7b46" in (
            route.calls[0].request.content.decode()
        )

    async def test_custom_tenant_url(self, mock_login_api, monkeypatch):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "teams_tenant_id", "tenant-123")
        tenant_url = (
            "https://login.microsoftonline.com/tenant-123/oauth2/v2.0/token"
        )
        mock_login_api.post(tenant_url).respond(
            200, json={"access_token": "at", "refresh_token": "rt"}
        )
        access, _ = await exchange_refresh_token()
        assert access == "at"


class TestAuthenticateSharepoint:
    async def test_success_posts_sharepoint_scope(self, mock_login_api, mock_github_api):
        route = mock_login_api.post(TOKEN_URL).respond(
            200,
            json={"access_token": "sp_at", "refresh_token": "rt3"},
        )
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").respond(
            200,
            json={"key": "dGVzdA==", "key_id": "k1"},
        )
        mock_github_api.put(
            "/repos/user/repo/actions/secrets/TEAMS_REFRESH_TOKEN"
        ).respond(200, text="ok")

        from teamsleech.services.auth import authenticate_sharepoint
        token = await authenticate_sharepoint("tenant.sharepoint.com")
        assert token == "sp_at"
        body = route.calls[0].request.content.decode()
        assert "tenant.sharepoint.com" in body

    async def test_failure_returns_none(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).respond(
            400,
            json={"error": "invalid_grant", "error_description": "Consent missing"},
        )
        from teamsleech.services.auth import authenticate_sharepoint
        assert await authenticate_sharepoint("tenant.sharepoint.com") is None

    async def test_no_refresh_token_returns_none(self, monkeypatch):
        from teamsleech.core.config import settings
        from teamsleech.services.auth import authenticate_sharepoint
        monkeypatch.setattr(settings, "teams_refresh_token", "")
        assert await authenticate_sharepoint("tenant.sharepoint.com") is None


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
        mock_github_api.put(
            "/repos/user/repo/actions/secrets/TEAMS_REFRESH_TOKEN"
        ).respond(200, text="ok")

        token = await authenticate()
        assert token == "at"

    async def test_secret_rotation_failure_is_nonfatal(
        self, mock_login_api, mock_github_api
    ):
        mock_login_api.post(TOKEN_URL).respond(
            200,
            json={"access_token": "at", "refresh_token": "rt"},
        )
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").mock(
            side_effect=httpx.RequestError("GitHub down")
        )

        token = await authenticate()
        assert token == "at"
