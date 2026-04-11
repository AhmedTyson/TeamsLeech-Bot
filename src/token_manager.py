"""
OAuth2 Token Manager.

Exchanges a Microsoft OAuth2 refresh_token for a Graph API access_token,
then auto-rotates the refresh_token back into GitHub Encrypted Secrets.

Public API
----------
get_access_token()                          → str
    All-in-one: exchange → rotate → return access_token.
exchange_refresh_token(refresh_token)       → (str, str)
    Exchange refresh_token for (access_token, new_refresh_token).
rotate_github_secret(rt, repo, pat)         → None
    Encrypt and write the new refresh_token to GitHub Secrets.
"""

import os
import base64
import logging
import requests
from nacl import encoding, public

# ───────────────────────── configuration ──────────────────────────

TENANT_ID  = "common"
CLIENT_ID  = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"   # Azure CLI
TOKEN_URL  = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
SCOPE      = "https://graph.microsoft.com/.default offline_access"

GITHUB_API = "https://api.github.com"
SECRET_NAME = "TEAMS_REFRESH_TOKEN"

log = logging.getLogger("token_manager")

# ───────────────────────── exceptions ─────────────────────────────

class TokenManagerError(Exception):
    """Base exception for all token_manager failures."""

class TokenExpiredError(TokenManagerError):
    """Raised when the refresh_token is fully expired (~90 days).
    Phase 3 should catch this and trigger the /reauth flow."""

class TokenExchangeError(TokenManagerError):
    """Raised for non-expiry auth failures (network, bad response, etc.)."""

class SecretRotationError(TokenManagerError):
    """Raised when writing the new refresh_token to GitHub Secrets fails.
    Phase 3/4 should catch this and send a Telegram alert."""

# ───────────────────────── core logic ─────────────────────────────

def exchange_refresh_token(refresh_token: str) -> tuple[str, str]:
    """Exchange a refresh_token for a fresh access_token.

    Returns
    -------
    (access_token, new_refresh_token)

    Raises
    ------
    TokenExpiredError   – refresh_token fully expired, user must /reauth
    TokenExchangeError  – any other auth failure
    """
    payload = {
        "client_id":     CLIENT_ID,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "scope":         SCOPE,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        resp = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=30)
    except requests.RequestException as exc:
        raise TokenExchangeError(f"Network error during token exchange: {exc}") from exc

    if resp.status_code != 200:
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        error_code = body.get("error", "")
        error_desc = body.get("error_description", resp.text[:200])

        if error_code == "invalid_grant":
            raise TokenExpiredError(
                f"Refresh token expired or revoked. Use /reauth to recover.\n{error_desc}"
            )
        raise TokenExchangeError(
            f"Token exchange failed [{resp.status_code}]: {error_code} — {error_desc}"
        )

    data = resp.json()
    access_token = data.get("access_token")
    new_refresh_token = data.get("refresh_token")

    if not access_token or not new_refresh_token:
        raise TokenExchangeError(
            "Token response missing access_token or refresh_token."
        )

    log.info("Token exchange successful — access_token acquired.")
    return access_token, new_refresh_token


def rotate_github_secret(
    new_refresh_token: str,
    repo: str,
    gh_pat: str,
) -> None:
    """Encrypt and save the new refresh_token to GitHub Secrets.

    Parameters
    ----------
    new_refresh_token : str
        The fresh refresh_token returned by Microsoft.
    repo : str
        GitHub repository in ``owner/repo`` format.
    gh_pat : str
        GitHub Personal Access Token with ``secrets:write`` scope.

    Raises
    ------
    SecretRotationError – any failure during encryption or API write
    """
    gh_headers = {
        "Authorization": f"Bearer {gh_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # 1. Fetch the repo's public key for secret encryption
    try:
        key_resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key",
            headers=gh_headers,
            timeout=15,
        )
        key_resp.raise_for_status()
    except requests.RequestException as exc:
        raise SecretRotationError(f"Failed to fetch GitHub public key: {exc}") from exc

    key_data = key_resp.json()
    public_key_b64 = key_data["key"]
    key_id = key_data["key_id"]

    # 2. Encrypt the secret using libsodium sealed box
    try:
        pub_key_bytes = base64.b64decode(public_key_b64)
        sealed_box = public.SealedBox(public.PublicKey(pub_key_bytes))
        encrypted = sealed_box.encrypt(new_refresh_token.encode("utf-8"))
        encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")
    except Exception as exc:
        raise SecretRotationError(f"Encryption failed: {exc}") from exc

    # 3. Write the encrypted secret
    try:
        put_resp = requests.put(
            f"{GITHUB_API}/repos/{repo}/actions/secrets/{SECRET_NAME}",
            headers=gh_headers,
            json={
                "encrypted_value": encrypted_b64,
                "key_id": key_id,
            },
            timeout=15,
        )
        put_resp.raise_for_status()
    except requests.RequestException as exc:
        raise SecretRotationError(
            f"Failed to update GitHub secret '{SECRET_NAME}': {exc}"
        ) from exc

    log.info("Refresh token rotated → GitHub secret '%s' updated.", SECRET_NAME)


# ───────────────────────── convenience ────────────────────────────

def get_access_token() -> str:
    """All-in-one entry point: exchange → rotate → return access_token.

    Reads from environment variables:
        TEAMS_REFRESH_TOKEN  – current refresh token
        GH_PAT               – GitHub PAT with secrets:write
        GITHUB_REPOSITORY    – owner/repo  (set automatically by Actions)

    Returns
    -------
    str – a valid Graph API access_token (~87 min lifetime)
    """
    refresh_token = os.environ.get("TEAMS_REFRESH_TOKEN")
    gh_pat        = os.environ.get("GH_PAT")
    repo          = os.environ.get("GITHUB_REPOSITORY", "")

    if not refresh_token:
        raise TokenManagerError("TEAMS_REFRESH_TOKEN env var is not set.")
    if not gh_pat:
        raise TokenManagerError("GH_PAT env var is not set.")

    access_token, new_refresh_token = exchange_refresh_token(refresh_token)
    rotate_github_secret(new_refresh_token, repo, gh_pat)

    return access_token
