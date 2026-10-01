"""Shared helpers for Telegram callback-data parsing."""

import re

_INDEX_RE = re.compile(r"^(?:ren|sug|srch_pg|del_subj|del_confirm):(\d+)$")
_TEAM_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def parse_callback_index(data: str | bytes | None) -> int | None:
    """Extract a non-negative integer index from callback data.

    Returns None for malformed payloads (`ren:abc`, `del_subj:-1`,
    bytes, empty) so handlers can answer gracefully instead of
    crashing on `int()`.
    """
    if not data or not isinstance(data, str):
        return None
    m = _INDEX_RE.match(data)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def callback_text(data: str | bytes | None) -> str | None:
    """Normalize pyrogram text payloads (`str | bytes | None`) to `str`."""
    if data is None:
        return None
    if isinstance(data, bytes):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return data


def is_valid_team_id(team_id: str | None) -> bool:
    """MS Teams ids are UUIDs; at minimum require a colon-free token."""
    if not team_id or ":" in team_id:
        return False
    return _TEAM_ID_RE.fullmatch(team_id) is not None
