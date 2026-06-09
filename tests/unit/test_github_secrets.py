import httpx
import pytest

from teamsleech.services.github_secrets import SecretRotationError, rotate_github_secret


class TestRotateGithubSecret:
    async def test_success(self, mock_github_api):
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").respond(
            200,
            json={"key": "NWVmNjFhZDAyYzU4NmE3YzE4YjU3ZDUzYzE1MjQzZjY=", "key_id": "k1"},
        )
        mock_github_api.put(
            "/repos/user/repo/actions/secrets/MY_SECRET"
        ).respond(201, json={})

        await rotate_github_secret("MY_SECRET", "new_value")
        assert mock_github_api["/repos/user/repo/actions/secrets/MY_SECRET"].called

    async def test_no_credentials(self, monkeypatch):
        from teamsleech.core.config import settings
        monkeypatch.setattr(settings, "gh_pat", "")
        # Should not raise — just warns and returns
        await rotate_github_secret("MY_SECRET", "new_value")

    async def test_get_public_key_fails(self, mock_github_api):
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").mock(
            side_effect=httpx.RequestError("Connection error")
        )
        with pytest.raises(SecretRotationError, match="public key"):
            await rotate_github_secret("MY_SECRET", "new_value")

    async def test_put_secret_fails(self, mock_github_api):
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").respond(
            200,
            json={"key": "NWVmNjFhZDAyYzU4NmE3YzE4YjU3ZDUzYzE1MjQzZjY=", "key_id": "k1"},
        )
        mock_github_api.put(
            "/repos/user/repo/actions/secrets/MY_SECRET"
        ).mock(side_effect=httpx.RequestError("PUT failed"))
        with pytest.raises(SecretRotationError, match="MY_SECRET"):
            await rotate_github_secret("MY_SECRET", "new_value")

    async def test_invalid_public_key_encoding(self, mock_github_api):
        mock_github_api.get("/repos/user/repo/actions/secrets/public-key").respond(
            200,
            json={"key": "!!!invalid-base64!!!", "key_id": "k1"},
        )
        with pytest.raises(SecretRotationError, match="Encryption"):
            await rotate_github_secret("MY_SECRET", "new_value")
