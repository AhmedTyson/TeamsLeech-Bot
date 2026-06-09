import base64
import logging

import httpx
from nacl import public

from teamsleech.core.config import settings
from teamsleech.core.retry import retry_http

log = logging.getLogger("github_secrets")

class SecretRotationError(Exception):
    """Raised when writing the new refresh_token to GitHub Secrets fails."""

GITHUB_API = "https://api.github.com"
GH_TIMEOUT = 15.0

@retry_http
async def _get_github(url: str, headers: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.get(url, headers=headers, timeout=GH_TIMEOUT)

@retry_http
async def _put_github(url: str, headers: dict[str, str], json_data: dict) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.put(url, headers=headers, json=json_data, timeout=GH_TIMEOUT)

async def rotate_github_secret(secret_name: str, new_value: str) -> None:
    """
    Encrypt and write a new value to a GitHub Secret automatically.
    """
    if not settings.gh_pat or not settings.github_repository:
        log.warning(f"GH_PAT or GITHUB_REPOSITORY missing. Skipping GitHub secret rotation for {secret_name}.")
        return

    headers = {
        "Authorization": f"Bearer {settings.gh_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    try:
        url = f"{GITHUB_API}/repos/{settings.github_repository}/actions/secrets/public-key"
        resp = await _get_github(url, headers)
        resp.raise_for_status()
        key_data = resp.json()
    except httpx.RequestError as exc:
        raise SecretRotationError(f"Failed to fetch GitHub public key: {exc}") from exc

    pub_key_b64 = key_data["key"]
    key_id = key_data["key_id"]

    try:
        pub_key_bytes = base64.b64decode(pub_key_b64)
        sealed_box = public.SealedBox(public.PublicKey(pub_key_bytes))
        encrypted = sealed_box.encrypt(new_value.encode("utf-8"))
        encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")
    except Exception as exc:
        raise SecretRotationError(f"Encryption failed: {exc}") from exc

    try:
        put_url = f"{GITHUB_API}/repos/{settings.github_repository}/actions/secrets/{secret_name}"
        put_resp = await _put_github(put_url, headers, {"encrypted_value": encrypted_b64, "key_id": key_id})
        put_resp.raise_for_status()
    except httpx.RequestError as exc:
        raise SecretRotationError(f"Failed to update GitHub secret '{secret_name}': {exc}") from exc

    log.info("GitHub secret '%s' updated successfully.", secret_name)
