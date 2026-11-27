"""Lightweight SharePoint session check using the saved browser cookies.

One unauthenticated-style GET against the tenant's /_api/web with the
saved Cookie header. 200 means the captured session still works; 401/403
or a redirect to login.microsoftonline.com means it expired and the owner
should run 🖥 Browser Login again. Used at boot and by /status so a dead
session surfaces as one clear message instead of a wall of download 401s.
"""

import json
import logging

import httpx

from teamsleech.core.config import settings
from teamsleech.services.cookies import cookie_header, load_cookies

log = logging.getLogger("session_probe")

PROBE_TIMEOUT = 15.0


def session_host(raw: str) -> str | None:
    """First tenant.sharepoint.com host found in the saved cookie domains."""
    try:
        data = json.loads(raw) if raw and raw.strip() else None
    except json.JSONDecodeError:
        return None
    items = data.get("cookies", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    for entry in items:
        if not isinstance(entry, dict):
            continue
        domain = str(entry.get("domain", "")).lstrip(".").lower()
        if (
            domain.endswith(".sharepoint.com")
            and domain.count(".") >= 2
            and not domain.startswith("login.")
        ):
            return domain
    return None


async def probe_sharepoint_session() -> tuple[bool, str]:
    """(ok, human-readable detail) for the saved SP_COOKIES_JSON session."""
    cookies = load_cookies(settings.sp_cookies_json)
    if not cookies:
        return False, "no saved cookies yet"
    host = session_host(settings.sp_cookies_json)
    if not host:
        return False, "no SharePoint cookies saved"
    url = f"https://{host}/_api/web?$select=Title"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={
                    "Cookie": cookie_header(cookies),
                    "Accept": "application/json;odata=nometadata",
                },
                timeout=PROBE_TIMEOUT,
                follow_redirects=False,
            )
    except Exception as exc:  # network/DNS — cannot judge the session
        log.warning("Session probe failed: %s", exc)
        return False, f"probe failed ({exc.__class__.__name__})"
    if resp.status_code == 200:
        return True, "session OK"
    location = resp.headers.get("location", "")
    if resp.status_code in (401, 403) or (
        resp.status_code in (301, 302, 303) and "login" in location.lower()
    ):
        return False, f"session expired (HTTP {resp.status_code})"
    return False, f"unexpected HTTP {resp.status_code}"
