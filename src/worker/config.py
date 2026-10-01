"""Explicit SharePoint folder inventory. Replaces SUBJECTS_JSON keyword match."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Folder:
    name: str
    url: str


def _valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.hostname or ""
    return parsed.scheme == "https" and host.endswith(".sharepoint.com")


def load_folders() -> list[Folder]:
    """Load from FOLDERS_JSON env (preferred) or folders.json file."""
    raw = os.environ.get("FOLDERS_JSON", "")
    if not raw:
        path = os.environ.get("FOLDERS_PATH", "folders.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                raw = f.read()
    if not raw.strip():
        msg = "No folders configured: set FOLDERS_JSON or provide folders.json."
        raise ValueError(msg)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"FOLDERS_JSON is not valid JSON: {exc}"
        raise ValueError(msg) from exc
    items = data.get("folders", data) if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        msg = "Folder list is empty."
        raise ValueError(msg)
    folders = []
    for entry in items:
        name = str(entry.get("name", "")).strip()
        url = str(entry.get("url", "")).strip()
        if not name or not _valid_url(url):
            msg = f"Bad folder entry: {entry!r}"
            raise ValueError(msg)
        folders.append(Folder(name=name, url=url.rstrip("/")))
    return folders
