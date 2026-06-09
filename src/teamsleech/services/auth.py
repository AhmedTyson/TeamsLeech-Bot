import logging

import httpx

from teamsleech.core.config import settings
from teamsleech.core.retry import retry_http
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
SECRET_NAME = "TEAMS_REFRESH_TOKEN"
MS_TIMEOUT = 30.0

@retry_http
async def _post_token(payload: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.post(TOKEN_URL, data=payload, timeout=MS_TIMEOUT)

async def exchange_refresh_token() -> tuple[str, str]:
    """
    Exchange the configured refresh_token for a fresh (access_token, new_refresh_token).
    """
    payload = {
        "client_id": settings.teams_client_id,
        "grant_type": "refresh_token",
        "refresh_token": settings.teams_refresh_token,
        "scope": SCOPE,
    }
    
    try:
        resp = await _post_token(payload)
    except httpx.RequestError as exc:
        raise TokenExchangeError(f"Network error during exchange: {exc}") from exc

    if resp.status_code != 200:
        body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
        error_code = body.get("error", "")
        error_desc = body.get("error_description", resp.text[:200])
        
        if error_code == "invalid_grant":
            raise TokenExpiredError(f"Refresh token expired or revoked.\n{error_desc}")
            
        raise TokenExchangeError(f"Token exchange failed [{resp.status_code}]: {error_code} - {error_desc}")
        
    data = resp.json()
    
    if not data.get("access_token") or not data.get("refresh_token"):
        raise TokenExchangeError("Token response missing access_token or refresh_token.")
        
    log.info("Token exchange successful — access_token acquired.")
    return data["access_token"], data["refresh_token"]

async def authenticate() -> str:
    """
    All-in-one entry point: exchange → rotate TEAMS_REFRESH_TOKEN → return access_token.
    """
    if not settings.teams_refresh_token:
        raise TokenManagerError("TEAMS_REFRESH_TOKEN env var is not set in config.")
        
    access_token, new_refresh = await exchange_refresh_token()
    
    try:
        await rotate_github_secret(SECRET_NAME, new_refresh)
    except Exception as e:
        log.error("Secret rotation failed (non-fatal): %s", e)
        
    return access_token
