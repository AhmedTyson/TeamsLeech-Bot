"""Browser-session cookies for SharePoint downloads.

Same approach as the proven `state`-branch worker: the user's exported
browser cookies (EditThisCookie / Cookie-Editor JSON) are sent as a Cookie
header, so SharePoint sees the exact session that downloads fine in the
browser. No Graph, no tokens involved.
"""

import json
import logging
from typing import Any

from teamsleech.core.config import settings

log = logging.getLogger("cookies")

COOKIE_SECRET = "SP_COOKIES_JSON"
# SharePoint refreshes these mid-session; a fresh pair extends the session.
SESSION_COOKIE_NAMES = frozenset({"FedAuth", "rtFa"})


def load_cookies(raw: str) -> list[dict[str, str]]:
    """Parse cookie JSON export into [{name, value}]. Returns [] when empty/invalid."""
    if not raw or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("SP_COOKIES_JSON is not valid JSON: %s", exc)
        return []
    items = data.get("cookies", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        log.warning("SP_COOKIES_JSON must be a JSON list of {name, value}.")
        return []
    cookies = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        cookies.append({"name": name, "value": str(entry.get("value", ""))})
    return cookies


def cookie_header(cookies: list[dict[str, Any]]) -> str:
    """Cookie dicts into one header value."""
    return "; ".join(
        f"{c['name']}={c['value']}" for c in cookies if c.get("name")
    )


def merge_refreshed_cookies(
    saved_raw: str, fresh: list[dict[str, Any]]
) -> tuple[str | None, list[str]]:
    """Merge refreshed values (from Set-Cookie responses) into the saved
    cookie export, preserving its original JSON shape. Session markers
    (FedAuth/rtFa) missing from the export are adopted. Returns
    (new_json, changed_names), or (None, []) when nothing changed or the
    saved export is unusable."""
    if not saved_raw or not saved_raw.strip():
        return None, []
    try:
        data = json.loads(saved_raw)
    except json.JSONDecodeError:
        return None, []
    wrapped = isinstance(data, dict)
    items = data.get("cookies") if wrapped else data
    if not isinstance(items, list):
        return None, []
    fresh_by_name = {
        str(c.get("name", "")): str(c.get("value", ""))
        for c in fresh
        if isinstance(c, dict) and c.get("name") and c.get("value")
    }
    if not fresh_by_name:
        return None, []
    changed: list[str] = []
    known: set[str] = set()
    for entry in items:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", ""))
        if not name:
            continue
        known.add(name)
        new_val = fresh_by_name.get(name)
        if new_val and new_val != entry.get("value"):
            entry["value"] = new_val
            changed.append(name)
    for name in sorted(SESSION_COOKIE_NAMES - known):
        if name in fresh_by_name:
            items.append({"name": name, "value": fresh_by_name[name]})
            changed.append(name)
    if not changed:
        return None, []
    if wrapped:
        data["cookies"] = items
        return json.dumps(data), changed
    return json.dumps(items), changed


async def persist_refreshed_cookies(fresh: list[dict[str, Any]]) -> list[str]:
    """Re-save SP_COOKIES_JSON when Set-Cookie responses during a run
    refreshed session cookies, so the next run inherits the extended
    session. Never raises: a failed re-save must not break a working
    download."""
    new_json, changed = merge_refreshed_cookies(settings.sp_cookies_json, fresh)
    if not changed or new_json is None:
        return []
    try:
        from teamsleech.services.github_secrets import rotate_github_secret

        await rotate_github_secret(COOKIE_SECRET, new_json)
    except Exception as exc:
        log.warning("Could not re-save refreshed cookies: %s", exc)
        return []
    settings.sp_cookies_json = new_json
    log.info(
        "Re-saved refreshed SharePoint cookies to %s: %s", COOKIE_SECRET, changed
    )
    return changed
