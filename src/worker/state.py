"""Committed-JSON dedup state. Replaces Telegram-pinned state."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any


def load(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def is_new(entry_id: str, state: dict[str, Any]) -> bool:
    return entry_id not in state


def mark(
    state: dict[str, Any], entry_id: str, name: str, tg_msg_id: int | None = None
) -> dict[str, Any]:
    state[entry_id] = {"name": name, "tg_msg_id": tg_msg_id}
    return state


def save(state: dict[str, Any], path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
