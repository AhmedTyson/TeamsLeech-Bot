"""
Phase 2 — fetcher (v2 — async)

Scans Microsoft Teams drives via the Graph API to find new .mp4 recordings
for each configured subject. Uses asyncio + httpx for concurrent scanning.

Flow
----
1. Load subject definitions from subjects_config.json
2. Call /me/joinedTeams (with @odata.nextLink pagination)
3. Filter teams whose displayName matches any subject keyword
4. For each matching team  →  list drives  →  search for .mp4 files (concurrent)
5. Filter files by date range or last_run timestamp
6. Return structured results grouped by subject

Public API
----------
fetch_recordings_async(...)  → dict  (async, preferred)
fetch_recordings(...)        → dict  (sync wrapper, backward compat)
load_subjects(path)          → list[dict]
save_last_run(...)           → None
get_current_week_range()     → tuple[str, str]
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

# ───────────────────────── constants ──────────────────────────────

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_CONCURRENT = 20  # Graph API rate-limit safe ceiling

log = logging.getLogger("fetcher")

# ───────────────────────── exceptions ─────────────────────────────

class FetcherError(Exception):
    """Base exception for fetcher failures."""

class GraphAPIError(FetcherError):
    """Raised when a Graph API call returns an unexpected error."""

# ───────────────────────── config loading ─────────────────────────

def load_subjects(path: str = "subjects_config.json") -> list[dict]:
    """Load subject definitions from JSON config.

    Each subject has: name, short, keywords[]
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    subjects = data.get("subjects", [])
    if not subjects:
        raise FetcherError(f"No subjects found in {path}")
    return subjects

# ───────────────────────── date helpers ────────────────────────────

def get_current_week_range() -> tuple[str, str]:
    """Return (monday_str, sunday_str) ISO dates for the current week."""
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()

# Local state filesystem functions removed to favor state_manager.py

# ───────────────────────── Async Graph API helpers ────────────────

async def _graph_get_async(
    client: httpx.AsyncClient,
    url: str,
    access_token: str,
    params: dict | None = None,
) -> dict:
    """Async GET a Graph API endpoint with Bearer auth. Returns JSON."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    try:
        resp = await client.get(url, headers=headers, params=params, timeout=30)
    except httpx.RequestError as exc:
        raise GraphAPIError(f"Network error: {exc}") from exc

    if resp.status_code != 200:
        raise GraphAPIError(
            f"Graph API error [{resp.status_code}]: {resp.text[:300]}"
        )
    return resp.json()

# ───────────────────────── team matching ──────────────────────────

def _match_teams_to_subject(
    teams: list[dict], subject: dict
) -> list[dict]:
    """Filter teams whose displayName contains any of the subject's keywords."""
    matched = []
    keywords = [kw.lower() for kw in subject.get("keywords", [])]
    for team in teams:
        name_lower = team.get("displayName", "").lower()
        if any(kw in name_lower for kw in keywords):
            matched.append(team)
    return matched

# ───────────────────────── concurrent team processor ──────────────

async def _process_team(
    client: httpx.AsyncClient,
    team: dict,
    access_token: str,
    last_run: datetime,
    date_start: str | None,
    date_end: str | None,
    seen_ids: set,
) -> list[dict]:
    """Fetch drives + search .mp4s for ONE team concurrently."""
    team_id = team["id"]
    team_name = team["displayName"]
    recordings = []

    # Step 1: get site
    try:
        site = await _graph_get_async(
            client,
            f"{GRAPH_BASE}/groups/{team_id}/sites/root",
            access_token,
        )
    except GraphAPIError as exc:
        log.warning("Could not get site for team %s: %s", team_id, exc)
        return []

    site_id = site.get("id", "")
    if not site_id:
        return []

    # Step 2: get drives
    try:
        drives_data = await _graph_get_async(
            client,
            f"{GRAPH_BASE}/sites/{site_id}/drives",
            access_token,
        )
    except GraphAPIError as exc:
        log.warning("Could not list drives for site %s: %s", site_id, exc)
        return []

    drives = drives_data.get("value", [])

    # Step 3: search all drives in this team concurrently
    async def search_drive(drive):
        drive_id = drive["id"]
        try:
            data = await _graph_get_async(
                client,
                f"{GRAPH_BASE}/drives/{drive_id}/root/search(q='.mp4')",
                access_token,
            )
        except GraphAPIError as exc:
            log.warning("Search failed for drive %s: %s", drive_id, exc)
            return drive_id, []
        items = [
            item for item in data.get("value", [])
            if item.get("name", "").lower().endswith(".mp4")
        ]
        return drive_id, items

    drive_results = await asyncio.gather(*[search_drive(d) for d in drives])

    for drive_id, items in drive_results:
        for item in items:
            item_id = item["id"]
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            created_str = item.get("createdDateTime", "")
            created_date_only = created_str[:10]  # YYYY-MM-DD
            time_only = created_str[11:16] if len(created_str) >= 16 else ""

            # Date filtering logic
            if date_start:
                if date_end:
                    # Range filter
                    if not (date_start <= created_date_only <= date_end):
                        continue
                else:
                    # Single date filter
                    if created_date_only != date_start:
                        continue
            else:
                # Normal: check against last_run
                try:
                    created_dt = datetime.fromisoformat(
                        created_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                if created_dt <= last_run:
                    continue

            size_bytes = item.get("size", 0)
            duration_ms = item.get("video", {}).get("duration", 0)
            
            recordings.append({
                "name": item["name"],
                "size_mb": round(size_bytes / (1024 * 1024), 1),
                "created": created_date_only,
                "time": time_only,
                "duration_ms": duration_ms,
                "drive_id": drive_id,
                "item_id": item_id,
                "team_name": team_name,
                "subject_name": subj_name,
            })

    return recordings

# ───────────────────────── async core ─────────────────────────────

async def fetch_recordings_async(
    access_token: str,
    subjects_path: str = "subjects_config.json",
    state_manager: "Any" = None,
    subject_filter: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
) -> dict[str, list[dict]]:
    """Async core: run all team scans concurrently with a shared httpx client.

    Parameters
    ----------
    access_token : str
        Valid Graph API Bearer token.
    subjects_path : str
        Path to subjects_config.json.
    state_manager : Any
        Instance of TelegramStateManager to get last_run records.
    subject_filter : str | None
        If provided, only scan this one subject.
    date_start : str | None
        If provided (YYYY-MM-DD), filter start date. If date_end is also
        set, acts as range start. Otherwise acts as exact date match.
    date_end : str | None
        If provided (YYYY-MM-DD), filter end date for range queries.

    Returns
    -------
    dict mapping subject name → list of recording dicts.
    """
    subjects = load_subjects(subjects_path)

    if subject_filter:
        filter_lower = subject_filter.lower()
        subjects = [
            s for s in subjects
            if s["name"].lower() == filter_lower
            or s.get("short", "").lower() == filter_lower
        ]
        if not subjects:
            raise FetcherError(
                f"No subject matches filter '{subject_filter}'. "
                "Check subjects_config.json."
            )

    limits = httpx.Limits(max_connections=MAX_CONCURRENT, max_keepalive_connections=10)
    results: dict[str, list[dict]] = {}

    async with httpx.AsyncClient(limits=limits) as client:
        # Fetch all joined teams once (single call + pagination)
        all_teams_data = await _graph_get_async(
            client, f"{GRAPH_BASE}/me/joinedTeams", access_token
        )
        all_teams = all_teams_data.get("value", [])
        next_link = all_teams_data.get("@odata.nextLink")
        while next_link:
            page = await _graph_get_async(client, next_link, access_token)
            all_teams.extend(page.get("value", []))
            next_link = page.get("@odata.nextLink")

        log.info("Fetched %d joined teams total.", len(all_teams))

        for subject in subjects:
            subj_name = subject["name"]
            last_run = state_manager.get_last_run(subj_name) if state_manager else datetime.min.replace(tzinfo=timezone.utc)
            matched_teams = _match_teams_to_subject(all_teams, subject)

            log.info(
                "Subject '%s': %d matching teams, last_run=%s",
                subj_name, len(matched_teams), last_run.isoformat(),
            )

            seen_ids: set[str] = set()

            # ALL teams for this subject fire concurrently
            team_results = await asyncio.gather(*[
                _process_team(
                    client, team, access_token,
                    last_run, date_start, date_end, seen_ids,
                )
                for team in matched_teams
            ])

            recordings = [r for batch in team_results for r in batch]
            recordings.sort(key=lambda r: r["created"], reverse=True)
            results[subj_name] = recordings

            log.info(
                "Subject '%s': found %d matched recording(s).",
                subj_name, len(recordings),
            )

    return results

# ───────────────────────── sync wrapper (backward compat) ─────────

def fetch_recordings(
    access_token: str,
    subjects_path: str = "subjects_config.json",
    state_dir: str = ".state",
    subject_filter: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    date_filter: str | None = None,  # backward compat alias
) -> dict[str, list[dict]]:
    """Sync wrapper around fetch_recordings_async.

    Accepts legacy `date_filter` param as alias for `date_start`.
    """
    if date_filter and not date_start:
        date_start = date_filter

    coro = fetch_recordings_async(
        access_token, subjects_path, state_dir,
        subject_filter, date_start, date_end,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Called from inside an already-running event loop (e.g. bot handler)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)
