import asyncio
import logging

import httpx
from pyrogram import Client

from teamsleech.core.config import settings
from teamsleech.services.auth import SECRET_NAME, client_id, device_code_url, token_url
from teamsleech.services.github_secrets import rotate_github_secret

log = logging.getLogger("reauth")

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
REAUTH_SCOPE = "offline_access https://graph.microsoft.com/.default"
MS_TIMEOUT = 30.0

# Back-compat for tests importing module constants.
DEVICE_CODE_URL = device_code_url()
TOKEN_URL = token_url()


class ReauthError(Exception):
    pass


async def request_device_code(scope: str = REAUTH_SCOPE) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                device_code_url(),
                data={"client_id": client_id(), "scope": scope},
                timeout=MS_TIMEOUT,
            )
    except httpx.RequestError as exc:
        raise ReauthError(f"Network error requesting device code: {exc}") from exc

    if resp.status_code != 200:
        raise ReauthError(
            f"Device code request failed [{resp.status_code}]: {resp.text[:200]}"
        )
    return resp.json()


async def poll_device_token(
    device_code: str, interval: int, expires_in: int
) -> dict:
    deadline = asyncio.get_event_loop().time() + expires_in
    async with httpx.AsyncClient() as client:
        while True:
            if asyncio.get_event_loop().time() >= deadline:
                raise ReauthError("Login timed out — rerun with mode=reauth.")
            try:
                resp = await client.post(
                    token_url(),
                    data={
                        "client_id": client_id(),
                        "grant_type": DEVICE_GRANT,
                        "device_code": device_code,
                    },
                    timeout=MS_TIMEOUT,
                )
            except httpx.RequestError as exc:
                raise ReauthError(f"Network error polling login: {exc}") from exc

            data = resp.json() if resp.status_code == 200 or "application/json" in resp.headers.get("content-type", "") else {}
            if resp.status_code == 200 and "refresh_token" in data:
                return data
            if data.get("error") == "authorization_pending":
                await asyncio.sleep(max(interval, 1))
                continue
            raise ReauthError(
                data.get("error_description", data.get("error", f"Login failed [{resp.status_code}]"))[:300]
            )


async def run_reauth_flow(app: Client, chat_id: int) -> bool:
    try:
        code_data = await request_device_code()
    except ReauthError as e:
        await app.send_message(chat_id, f"❌ Could not start Microsoft login: {e}")
        return False

    await app.send_message(
        chat_id,
        "🔑 **Microsoft login needed**\n\n"
        f"1. Open: {code_data.get('verification_uri')}\n"
        f"2. Enter code: `{code_data.get('user_code')}`\n\n"
        "_Code expires in ~15 minutes._",
    )

    try:
        tokens = await poll_device_token(
            code_data["device_code"],
            int(code_data.get("interval", 5)),
            int(code_data.get("expires_in", 900)),
        )
    except ReauthError as e:
        await app.send_message(chat_id, f"❌ Microsoft login failed: {e}")
        return False

    new_refresh = tokens.get("refresh_token")
    if not new_refresh:
        await app.send_message(chat_id, "❌ Login returned no session — try again.")
        return False

    settings.teams_refresh_token = new_refresh
    try:
        await rotate_github_secret(SECRET_NAME, new_refresh)
    except Exception as e:
        log.error("Secret rotation failed (non-fatal): %s", e)
        await app.send_message(
            chat_id,
            "⚠️ Logged in for this run only — saving the session failed. "
            "Rerun with mode=reauth before the next run.",
        )
        return True

    await app.send_message(
        chat_id, "✅ Logged in — saved. Future runs use the new Microsoft session."
    )
    return True
