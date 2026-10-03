from unittest.mock import AsyncMock

import httpx
import pytest

from teamsleech.services.reauth import (
    DEVICE_CODE_URL,
    TOKEN_URL,
    ReauthError,
    poll_device_token,
    request_device_code,
    run_reauth_flow,
)


def _device_code(**over):
    data = {
        "user_code": "ABC-123",
        "verification_uri": "https://microsoft.com/devicelogin",
        "device_code": "dc1",
        "expires_in": 900,
        "interval": 0,
    }
    data.update(over)
    return data


class TestRequestDeviceCode:
    async def test_success(self, mock_login_api):
        mock_login_api.post(DEVICE_CODE_URL).respond(200, json=_device_code())
        data = await request_device_code()
        assert data["user_code"] == "ABC-123"

    async def test_http_error(self, mock_login_api):
        mock_login_api.post(DEVICE_CODE_URL).respond(400, text="bad")
        with pytest.raises(ReauthError, match="400"):
            await request_device_code()

    async def test_network_error(self, mock_login_api):
        mock_login_api.post(DEVICE_CODE_URL).mock(
            side_effect=httpx.RequestError("down")
        )
        with pytest.raises(ReauthError, match="down"):
            await request_device_code()


class TestPollDeviceToken:
    async def test_pending_then_success(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).mock(
            side_effect=[
                httpx.Response(200, json={"error": "authorization_pending"}),
                httpx.Response(
                    200,
                    json={"access_token": "at", "refresh_token": "rt_new"},
                ),
            ]
        )
        data = await poll_device_token("dc1", 0, 60)
        assert data["refresh_token"] == "rt_new"

    async def test_declined(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).respond(
            400,
            json={"error": "access_denied", "error_description": "declined"},
        )
        with pytest.raises(ReauthError, match="declined"):
            await poll_device_token("dc1", 0, 60)

    async def test_timeout(self, mock_login_api):
        mock_login_api.post(TOKEN_URL).respond(
            200, json={"error": "authorization_pending"}
        )
        with pytest.raises(ReauthError, match="timed out"):
            await poll_device_token("dc1", 0, 0)


class TestRunReauthFlow:
    async def test_success_rotates_and_updates(
        self, mock_login_api, mock_github_api, monkeypatch
    ):
        import base64

        from nacl.public import PrivateKey

        from teamsleech.core.config import settings
        pub_b64 = base64.b64encode(bytes(PrivateKey.generate().public_key)).decode()
        monkeypatch.setattr(settings, "teams_refresh_token", "rt_old")
        mock_login_api.post(DEVICE_CODE_URL).respond(200, json=_device_code())
        mock_login_api.post(TOKEN_URL).respond(
            200, json={"access_token": "at", "refresh_token": "rt_new"}
        )
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").respond(
            200, json={"key": pub_b64, "key_id": "k1"}
        )
        mock_github_api.put(
            "/repos/user/repo/actions/secrets/TEAMS_REFRESH_TOKEN"
        ).respond(200, text="ok")

        app = AsyncMock()
        assert await run_reauth_flow(app, 123) is True
        assert settings.teams_refresh_token == "rt_new"
        first_text = app.send_message.await_args_list[0].args[1]
        assert "ABC-123" in first_text
        assert app.send_message.await_args_list[-1].args[1].startswith("✅")

    async def test_device_code_failure(self, mock_login_api):
        mock_login_api.post(DEVICE_CODE_URL).respond(400, text="bad")
        app = AsyncMock()
        assert await run_reauth_flow(app, 123) is False
        assert app.send_message.await_args.args[1].startswith("❌")

    async def test_rotation_failure_still_returns_true(
        self, mock_login_api, mock_github_api, monkeypatch
    ):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "teams_refresh_token", "rt_old")
        mock_login_api.post(DEVICE_CODE_URL).respond(200, json=_device_code())
        mock_login_api.post(TOKEN_URL).respond(
            200, json={"access_token": "at", "refresh_token": "rt_new"}
        )
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").mock(
            side_effect=httpx.RequestError("GitHub down")
        )
        app = AsyncMock()
        assert await run_reauth_flow(app, 123) is True
        assert app.send_message.await_args_list[-1].args[1].startswith("⚠️")
