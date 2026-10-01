"""Download SharePoint files with browser-session cookies. No Graph/tokens."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from worker.lister import cookie_header


def download_url(site: str, unique_id: str) -> str:
    """Bare download.aspx URL (browser-HAR parity: UniqueId only)."""
    return site.rstrip("/") + "/_layouts/15/download.aspx?UniqueId=" + unique_id


def download(
    url: str,
    cookies: list[dict[str, Any]],
    dest_path: str,
    client: httpx.Client,
    chunk_size: int = 1024 * 1024,
) -> tuple[int, str]:
    """Stream URL to dest with cookies + Range resume. Returns (bytes, sha256).

    Raises PermissionError on 401 (re-bootstrap cookies), other HTTP errors
    propagate via raise_for_status.
    """
    headers = {"Cookie": cookie_header(cookies)}
    start = 0
    if os.path.exists(dest_path):
        start = os.path.getsize(dest_path)
        if start:
            headers["Range"] = f"bytes={start}-"
    with client.stream("GET", url, headers=headers, timeout=120.0) as resp:
        if resp.status_code == 401:
            msg = f"Session rejected (401) for {url}: re-bootstrap cookies."
            raise PermissionError(msg)
        if resp.status_code == 416:
            return start, _sha256(dest_path)
        resp.raise_for_status()
        resume = bool(start) and resp.status_code == 206
        digest = hashlib.sha256()
        if resume:
            digest.update(_read_all(dest_path))
        else:
            start = 0
        written = start
        with open(dest_path, "ab" if resume else "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=chunk_size):
                f.write(chunk)
                digest.update(chunk)
                written += len(chunk)
        return written, digest.hexdigest()


def _read_all(path: str, chunk_size: int = 1024 * 1024) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _sha256(path: str) -> str:
    return hashlib.sha256(_read_all(path)).hexdigest()
