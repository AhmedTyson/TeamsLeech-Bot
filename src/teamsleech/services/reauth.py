"""Interactive Microsoft re-authorization via OAuth2 Device Code flow.

Used by ``workflow_dispatch`` with ``mode=reauth``: the bot sends the
user code to the owner over Telegram, waits for browser approval, then
injects the fresh refresh token into GitHub Secrets. Secrets are never
logged or printed.
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx
from pyrogram.client import Client

from teamsleech.core.config import settings
from teamsleech.services.auth import SCOPE, SECRET_NAME, TENANT_ID, TOKEN_URL
from teamsleech.services.github_secrets import SecretRotationError, rotate_github_secret

log = logging.getLogger("reauth")

DEVICE_CODE_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
REQUEST_TIMEOUT = 30.0

CodeCallback = Callable[[str, str], Awaitable[None]]


class ReauthError(Exception):
    pass


async def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=data, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        msg = f"Microsoft endpoint [{resp.status_code}]"
        raise ReauthError(msg)
    try:
        return cast("dict[str, Any]", resp.json())
    except ValueError as exc:
        msg = f"Microsoft response was not JSON: {exc}"
        raise ReauthError(msg) from exc


async def request_device_code() -> dict[str, Any]:
    data = await _post_form(
        DEVICE_CODE_URL, {"client_id": settings.teams_client_id, "scope": SCOPE}
    )
    for key in ("user_code", "verification_uri", "device_code"):
        if not data.get(key):
            msg = f"Device code response missing {key}."
            raise ReauthError(msg)
    return data


async def _poll_loop(
    device_code: str, interval: float, expires_in: float
) -> tuple[str, str] | None:
    deadline = asyncio.get_running_loop().time() + expires_in
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(interval)
        try:
            result = await _post_form(
                TOKEN_URL,
                {
                    "client_id": settings.teams_client_id,
                    "grant_type": DEVICE_GRANT,
                    "device_code": device_code,
                },
            )
        except (httpx.RequestError, ReauthError) as e:
            log.warning("Device poll failed, retrying: %s", e)
            continue
        error = result.get("error", "")
        if not error:
            access = result.get("access_token")
            refresh = result.get("refresh_token")
            if isinstance(access, str) and isinstance(refresh, str):
                return access, refresh
            log.error("Device flow returned incomplete tokens.")
            return None
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5.0
            continue
        log.error("Device flow ended: %s", result.get("error_description", error))
        return None
    log.error("Device flow timed out waiting for approval.")
    return None


async def run_device_reauth(on_code: CodeCallback) -> tuple[str, str] | None:
    """Run the full device flow; returns (access, refresh) or None."""
    try:
        challenge = await request_device_code()
    except (httpx.RequestError, ReauthError):
        log.exception("Could not start device flow")
        return None
    await on_code(challenge["verification_uri"], challenge["user_code"])
    try:
        interval = max(float(challenge.get("interval", 5)), 0.01)
        expires_in = float(challenge.get("expires_in", 900))
    except (TypeError, ValueError):
        log.exception("Device challenge has invalid timing fields.")
        return None
    return await _poll_loop(challenge["device_code"], interval, expires_in)


async def run_reauth_flow(app: Client, chat_id: int) -> bool:
    """Send code via Telegram, wait for approval, inject the secret."""

    async def _send_code(uri: str, code: str) -> None:
        await app.send_message(
            chat_id,
            "🔐 **Re-authorization needed**\n\n"
            f"1. Open: {uri}\n"
            f"2. Enter code: `{code}`\n\n"
            "_Approve in your browser — waiting up to 15 min._",
        )

    result = await run_device_reauth(_send_code)
    if result is None:
        await app.send_message(
            chat_id, "❌ Re-authorization failed or timed out. Run again when ready."
        )
        return False
    _, refresh = result

    settings.teams_refresh_token = refresh
    os.environ["TEAMS_REFRESH_TOKEN"] = refresh
    try:
        await rotate_github_secret(SECRET_NAME, refresh)
    except SecretRotationError as e:
        await app.send_message(
            chat_id,
            f"⚠️ Signed in, but secret injection failed: {e}\nSave the token from logs manually.",
        )
        return False
    await app.send_message(chat_id, "✅ Signed in! Fresh token injected into TEAMS_REFRESH_TOKEN.")
    return True
