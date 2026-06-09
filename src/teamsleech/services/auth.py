import base64
import logging
import httpx

from nacl import public

from teamsleech.core.config import settings

log = logging.getLogger("auth")

class TokenManagerError(Exception): 
    """Base exception for all token_manager failures."""

class TokenExpiredError(TokenManagerError): 
    """Raised when the refresh_token is fully expired (~90 days)."""

class TokenExchangeError(TokenManagerError): 
    """Raised for non-expiry auth failures (network, bad response, etc.)."""

class SecretRotationError(TokenManagerError): 
    """Raised when writing the new refresh_token to GitHub Secrets fails."""

TENANT_ID = "common"
CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # Azure CLI
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
SCOPE = "https://graph.microsoft.com/.default offline_access"
GITHUB_API = "https://api.github.com"
SECRET_NAME = "TEAMS_REFRESH_TOKEN"

async def exchange_refresh_token() -> tuple[str, str]:
    """
    Exchange the configured refresh_token for a fresh (access_token, new_refresh_token).
    """
    payload = {
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": settings.teams_refresh_token,
        "scope": SCOPE,
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(TOKEN_URL, data=payload, timeout=30.0)
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
    
    async with httpx.AsyncClient() as client:
        try:
            url = f"{GITHUB_API}/repos/{settings.github_repository}/actions/secrets/public-key"
            resp = await client.get(url, headers=headers, timeout=15)
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
            put_resp = await client.put(
                put_url,
                headers=headers,
                json={"encrypted_value": encrypted_b64, "key_id": key_id},
                timeout=15
            )
            put_resp.raise_for_status()
        except httpx.RequestError as exc:
            raise SecretRotationError(f"Failed to update GitHub secret '{secret_name}': {exc}") from exc
            
    log.info("GitHub secret '%s' updated successfully.", secret_name)

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
