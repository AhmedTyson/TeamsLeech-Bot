"""Subjects JSON store: readable/writable GitHub Gist, secret fallback.

Why: GitHub Secrets are write-only — nobody (not even the owner) can read
SUBJECTS_JSON back, so keyword configs go blind. A gist is visible and
editable in the browser; the bot reads it at runtime and writes it back on
add/edit/delete. Set SUBJECTS_URL to the raw file URL, e.g.
https://gist.githubusercontent.com/AhmedTyson/<hash>/raw/subjects.json
"""

import logging
import re

import httpx

from teamsleech.core.config import settings

log = logging.getLogger("subjects_store")

GIST_API = "https://api.github.com"
STORE_TIMEOUT = 30.0


def parse_gist_ref(url: str) -> tuple[str, str]:
    """Raw gist URL -> (gist_id, filename)."""
    m = re.match(
        r"https://gist\.githubusercontent\.com/[^/]+/([^/]+)/raw(?:/[^/]+)?/(.+)",
        (url or "").strip(),
    )
    if not m:
        raise ValueError(
            "SUBJECTS_URL must be a raw gist file URL like "
            "https://gist.githubusercontent.com/<user>/<hash>/raw/subjects.json"
        )
    return m.group(1), m.group(2)


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if settings.gh_pat:
        headers["Authorization"] = f"Bearer {settings.gh_pat}"
    return headers


def fetch_gist_text(url: str) -> str:
    with httpx.Client() as client:
        resp = client.get(
            url, headers=_github_headers(), timeout=STORE_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text


def push_gist_text(url: str, content: str) -> None:
    gist_id, filename = parse_gist_ref(url)
    if not settings.gh_pat:
        raise ValueError("GH_PAT is not configured.")
    with httpx.Client() as client:
        resp = client.patch(
            f"{GIST_API}/gists/{gist_id}",
            headers=_github_headers(),
            json={"files": {filename: {"content": content}}},
            timeout=STORE_TIMEOUT,
        )
        if resp.status_code in (403, 404):
            raise ValueError(
                "Gist write denied — your GH_PAT needs the 'gist' scope"
                " (classic token) or Gists read/write (fine-grained)."
            )
        resp.raise_for_status()


def load_subjects_text() -> str:
    """Gist URL wins; otherwise the SUBJECTS_JSON secret/env value."""
    if settings.subjects_url.strip():
        return fetch_gist_text(settings.subjects_url.strip())
    return settings.subjects_json


def save_subjects_text(content: str) -> str:
    """Persist via gist when configured, else the secret. Returns source."""
    if settings.subjects_url.strip():
        push_gist_text(settings.subjects_url.strip(), content)
        return "gist"
    import asyncio

    from teamsleech.services.github_secrets import rotate_github_secret

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(rotate_github_secret("SUBJECTS_JSON", content))
        return "secret"

    # Called from async context: caller awaits instead.
    raise RuntimeError("Use await save_subjects_text_async() inside async code.")


async def save_subjects_text_async(content: str) -> str:
    """Async variant for handlers already running in a loop."""
    if settings.subjects_url.strip():
        import asyncio as _aio

        await _aio.to_thread(push_gist_text, settings.subjects_url.strip(), content)
        return "gist"

    from teamsleech.services.github_secrets import rotate_github_secret

    await rotate_github_secret("SUBJECTS_JSON", content)
    return "secret"
