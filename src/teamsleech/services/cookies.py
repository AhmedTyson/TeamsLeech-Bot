"""Browser-session cookies for SharePoint downloads.

Same approach as the proven `state`-branch worker: the user's exported
browser cookies (EditThisCookie / Cookie-Editor JSON) are sent as a Cookie
header, so SharePoint sees the exact session that downloads fine in the
browser. No Graph, no tokens involved.
"""

import json
import logging
from typing import Any

log = logging.getLogger("cookies")


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
