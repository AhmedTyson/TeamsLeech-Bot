from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from teamsleech.services.reauth import (
    ReauthError,
    request_device_code,
    run_device_reauth,
    run_reauth_flow,
)

DEVICE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


def _challenge(**kw):
    base = {
        "user_code": "ABCD-1234",
        "verification_uri": "https://microsoft.com/devicelogin",
        "device_code": "dev-code-1",
        "expires_in": 30,
        "interval": 0.01,
    }
    base.update(kw)
    return base


class TestDeviceFlow:
    async def test_success(self, mock_login_api):
        mock_login_api.post(DEVICE_URL).respond(200, json=_challenge())
        route = mock_login_api.post(TOKEN_URL)
        route.side_effect = [
            httpx.Response(200, json={"error": "authorization_pending"}),
            httpx.Response(200, json={"access_token": "at", "refresh_token": "rt"}),
        ]
        seen = []

        async def on_code(uri, code):
            seen.append((uri, code))

        result = await run_device_reauth(on_code)
        assert result == ("at", "rt")
        assert seen == [("https://microsoft.com/devicelogin", "ABCD-1234")]

    async def test_declined_returns_none(self, mock_login_api):
        mock_login_api.post(DEVICE_URL).respond(200, json=_challenge())
        mock_login_api.post(TOKEN_URL).respond(200, json={"error": "authorization_declined"})
        assert await run_device_reauth(AsyncMock()) is None

    async def test_expired_challenge_returns_none(self, mock_login_api):
        mock_login_api.post(DEVICE_URL).respond(200, json=_challenge(expires_in=0))
        assert await run_device_reauth(AsyncMock()) is None

    async def test_device_code_http_error(self, mock_login_api):
        mock_login_api.post(DEVICE_URL).respond(500, text="oops")
        assert await run_device_reauth(AsyncMock()) is None

    async def test_missing_keys_raise(self, mock_login_api):
        mock_login_api.post(DEVICE_URL).respond(200, json={"user_code": "x"})
        with pytest.raises(ReauthError, match="verification_uri"):
            await request_device_code()


class TestReauthFlow:
    async def test_success_injects_secret(self):
        from teamsleech.core.config import settings

        app = MagicMock()
        app.send_message = AsyncMock()
        with (
            patch(
                "teamsleech.services.reauth.run_device_reauth",
                new=AsyncMock(return_value=("at", "rt_new")),
            ),
            patch(
                "teamsleech.services.reauth.rotate_github_secret",
                new=AsyncMock(),
            ) as rotate,
        ):
            assert await run_reauth_flow(app, 123) is True
        assert settings.teams_refresh_token == "rt_new"
        rotate.assert_awaited_once()
        texts = [c.args[1] for c in app.send_message.await_args_list]
        assert any("injected" in t for t in texts)

    async def test_decline_returns_false(self):
        app = MagicMock()
        app.send_message = AsyncMock()
        with patch(
            "teamsleech.services.reauth.run_device_reauth",
            new=AsyncMock(return_value=None),
        ):
            assert await run_reauth_flow(app, 123) is False

    async def test_rotation_failure_returns_false(self):
        from teamsleech.services.github_secrets import SecretRotationError

        app = MagicMock()
        app.send_message = AsyncMock()
        with (
            patch(
                "teamsleech.services.reauth.run_device_reauth",
                new=AsyncMock(return_value=("at", "rt_new")),
            ),
            patch(
                "teamsleech.services.reauth.rotate_github_secret",
                new=AsyncMock(side_effect=SecretRotationError("no pat")),
            ),
        ):
            assert await run_reauth_flow(app, 123) is False
