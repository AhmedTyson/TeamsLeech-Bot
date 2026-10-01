"""List SharePoint folder contents with browser-session cookies. No Graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import httpx

REST_HEADERS = {"Accept": "application/json;odata=verbose"}


@dataclass(frozen=True)
class FileEntry:
    name: str
    unique_id: str
    size: int
    modified: str
    server_path: str


def folder_api_url(folder_url: str) -> str:
    """REST Files endpoint for a SharePoint folder URL."""
    parsed = urlparse(folder_url)
    if parsed.scheme != "https" or not parsed.hostname:
        msg = f"Bad folder URL: {folder_url}"
        raise ValueError(msg)
    base = f"{parsed.scheme}://{parsed.hostname}"
    cut = parsed.path.find("/Shared Documents/")
    if cut < 0:
        cut = parsed.path.find("/SharedDocuments/")
    if cut < 0:
        msg = f"URL is not a Shared Documents folder: {folder_url}"
        raise ValueError(msg)
    site = parsed.path[:cut]
    rel = parsed.path.replace("'", "''")
    endpoint = "/_api/web/GetFolderByServerRelativeUrl('" + quote(rel) + "')/Files"
    return base + site + endpoint


def parse_files(payload: dict[str, Any]) -> list[FileEntry]:
    """Parse a verbose-JSON Files response into entries."""
    results = payload.get("d", {}).get("results", [])
    entries = []
    for item in results:
        name = str(item.get("Name", ""))
        if not name:
            continue
        try:
            size = int(item.get("Length", 0))
        except (TypeError, ValueError):
            size = 0
        entries.append(
            FileEntry(
                name=name,
                unique_id=str(item.get("UniqueId", "")),
                size=size,
                modified=str(item.get("TimeLastModified", "")),
                server_path=str(item.get("ServerRelativeUrl", "")),
            )
        )
    return entries


def cookie_header(cookies: list[dict[str, Any]]) -> str:
    """Netscape-jar dicts (name/value) into one Cookie header."""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))


def list_folder(
    folder_url: str, cookies: list[dict[str, Any]], client: httpx.Client
) -> list[FileEntry]:
    """GET the Files endpoint with session cookies; loud on auth failure."""
    resp = client.get(
        folder_api_url(folder_url),
        headers={**REST_HEADERS, "Cookie": cookie_header(cookies)},
        timeout=60.0,
    )
    if resp.status_code == 401:
        msg = f"Session rejected (401) for {folder_url}: re-bootstrap cookies."
        raise PermissionError(msg)
    resp.raise_for_status()
    return parse_files(resp.json())
