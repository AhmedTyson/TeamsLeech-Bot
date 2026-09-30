import json
import logging
import os
from typing import Any, cast

import httpx

from teamsleech.core.config import settings
from teamsleech.core.retry import _http_status_error, honor_retry_after, retry_http
from teamsleech.services.github_secrets import rotate_github_secret

log = logging.getLogger("auth")


class TokenManagerError(Exception):
    """Base exception for all token_manager failures."""


class TokenExpiredError(TokenManagerError):
    """Raised when the refresh_token is fully expired (~90 days)."""


class TokenExchangeError(TokenManagerError):
    """Raised for non-expiry auth failures (network, bad response, etc.)."""


TENANT_ID = "common"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
SCOPE = "https://graph.microsoft.com/.default offline_access"
SECRET_NAME = "TEAMS_REFRESH_TOKEN"  # noqa: S105 - secret *name*, not a value
MS_TIMEOUT = 30.0


@retry_http
async def _post_token(payload: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data=payload, timeout=MS_TIMEOUT)
        if resp.status_code == 429 or resp.status_code >= 500:
            await honor_retry_after(resp)
            msg = f"Token endpoint throttled [{resp.status_code}]"
            raise _http_status_error(msg, resp)
        return resp


async def _exchange_token(scope: str) -> dict[str, Any]:
    payload = {
        "client_id": settings.teams_client_id,
        "grant_type": "refresh_token",
        "refresh_token": settings.teams_refresh_token,
        "scope": scope,
    }

    try:
        resp = await _post_token(payload)
    except httpx.HTTPStatusError as exc:
        msg = f"Token endpoint failed after retries: {exc}"
        raise TokenExchangeError(msg) from exc
    except httpx.RequestError as exc:
        msg = f"Network error during exchange: {exc}"
        raise TokenExchangeError(msg) from exc

    if resp.status_code != 200:
        content_type = resp.headers.get("content-type", "")
        try:
            body = resp.json() if "application/json" in content_type else {}
        except (json.JSONDecodeError, ValueError):
            body = {}
        error_code = body.get("error", "") or f"http_{resp.status_code}"
        # Structured OAuth error fields only — never echo raw bodies.
        error_desc = body.get("error_description", "") or error_code

        if error_code == "invalid_grant":
            msg = f"Refresh token expired or revoked.\n{error_desc}"
            raise TokenExpiredError(msg)

        msg = f"Token exchange failed [{resp.status_code}]: {error_code}"
        raise TokenExchangeError(msg)

    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        msg = f"Token response was not valid JSON: {exc}"
        raise TokenExchangeError(msg) from exc

    return cast("dict[str, Any]", data)


async def exchange_refresh_token() -> tuple[str, str]:
    """
    Exchange the configured refresh_token for a fresh (access_token, new_refresh_token).
    """
    data = await _exchange_token(SCOPE)

    if not data.get("access_token") or not data.get("refresh_token"):
        msg = "Token response missing access_token or refresh_token."
        raise TokenExchangeError(msg)

    log.info("Token exchange successful — access_token acquired.")
    return data["access_token"], data["refresh_token"]


async def exchange_sharepoint_token(host: str) -> tuple[str, str]:
    """Access token with SharePoint audience plus rotated refresh token.

    Same refresh-token chain as the Graph exchange: the caller must
    persist the returned refresh token (secret rotation) immediately,
    or the next boot reuses a stale token.
    """
    data = await _exchange_token(f"https://{host}/.default offline_access")

    if not data.get("access_token") or not data.get("refresh_token"):
        msg = "SharePoint token response missing access_token or refresh_token."
        raise TokenExchangeError(msg)

    log.info("SharePoint token exchange successful for %s.", host)
    return data["access_token"], data["refresh_token"]


V1_TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/token"


async def exchange_sharepoint_token_v1(host: str) -> tuple[str, str | None]:
    """v1 resource-style token for SharePoint setups rejecting v2 tokens.

    Returns (access_token, new_refresh_token|None). A missing refresh
    token keeps the current chain untouched by the caller.
    """
    payload = {
        "client_id": settings.teams_client_id,
        "grant_type": "refresh_token",
        "refresh_token": settings.teams_refresh_token,
        "resource": f"https://{host}",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(V1_TOKEN_URL, data=payload, timeout=MS_TIMEOUT)
    except httpx.RequestError as exc:
        msg = f"Network error during v1 exchange: {exc}"
        raise TokenExchangeError(msg) from exc

    if resp.status_code != 200:
        try:
            body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
        except (json.JSONDecodeError, ValueError):
            body = {}
        error_code = body.get("error", "") or f"http_{resp.status_code}"
        error_desc = body.get("error_description", "") or error_code
        if error_code == "invalid_grant":
            msg = f"Refresh token expired or revoked.\n{error_desc}"
            raise TokenExpiredError(msg)
        msg = f"SharePoint v1 exchange failed [{resp.status_code}]: {error_code}"
        raise TokenExchangeError(msg)

    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        msg = f"SharePoint v1 response was not valid JSON: {exc}"
        raise TokenExchangeError(msg) from exc

    access = data.get("access_token")
    if not isinstance(access, str):
        msg = "SharePoint v1 response missing access_token."
        raise TokenExchangeError(msg)
    new_refresh = data.get("refresh_token")
    return access, new_refresh if isinstance(new_refresh, str) else None


async def authenticate() -> str:
    """
    All-in-one entry point: exchange → rotate TEAMS_REFRESH_TOKEN → return access_token.
    """
    if not settings.teams_refresh_token:
        msg = "TEAMS_REFRESH_TOKEN env var is not set in config."
        raise TokenManagerError(msg)

    access_token, new_refresh = await exchange_refresh_token()

    try:
        await rotate_github_secret(SECRET_NAME, new_refresh)
    except Exception:
        settings.teams_refresh_token = new_refresh
        os.environ["TEAMS_REFRESH_TOKEN"] = new_refresh
        log.exception(
            "Secret rotation failed — new refresh token kept in-process only. "
            "Update TEAMS_REFRESH_TOKEN manually or next restart reuses "
            "the stale token."
        )

    return access_token
