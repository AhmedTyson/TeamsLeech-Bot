"""
Phase 2 — fetcher

Scans Microsoft Teams drives via the Graph API to find new .mp4 recordings
for each configured subject.

Flow
----
1. Load subject definitions from subjects_config.json
2. Call /me/joinedTeams (with @odata.nextLink pagination)
3. Filter teams whose displayName matches any subject keyword
4. For each matching team  →  list drives  →  search for .mp4 files
5. Filter files newer than the per-subject last_run timestamp
6. Return structured results grouped by subject

Public API
----------
fetch_recordings(access_token, subjects_path, state_dir) → dict
load_subjects(path)                                      → list[dict]
save_last_run(state_dir, subject_name, timestamp)        → None
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests

# ───────────────────────── constants ──────────────────────────────

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

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

# ───────────────────────── state management ───────────────────────

def _state_file(state_dir: str, subject_name: str) -> str:
    """Return path to per-subject last_run file."""
    safe_name = subject_name.replace(" ", "_").lower()
    return os.path.join(state_dir, f"last_run_{safe_name}.txt")


def get_last_run(state_dir: str, subject_name: str) -> datetime:
    """Read the last_run timestamp for a subject.

    Returns datetime.min (UTC) if no state file exists (first run).
    """
    path = _state_file(state_dir, subject_name)
    if not os.path.exists(path):
        return datetime.min.replace(tzinfo=timezone.utc)
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        log.warning("Invalid timestamp in %s, treating as first run.", path)
        return datetime.min.replace(tzinfo=timezone.utc)


def save_last_run(
    state_dir: str, subject_name: str, timestamp: datetime | None = None
) -> None:
    """Write the current UTC timestamp as last_run for a subject."""
    os.makedirs(state_dir, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc)
    path = _state_file(state_dir, subject_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(ts.isoformat())
    log.info("Saved last_run for '%s' → %s", subject_name, ts.isoformat())

# ───────────────────────── Graph API helpers ──────────────────────

def _graph_get(
    url: str, access_token: str, params: dict | None = None
) -> dict:
    """GET a Graph API endpoint with Bearer auth. Returns JSON."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
    except requests.RequestException as exc:
        raise GraphAPIError(f"Network error: {exc}") from exc

    if resp.status_code != 200:
        raise GraphAPIError(
            f"Graph API error [{resp.status_code}]: {resp.text[:300]}"
        )
    return resp.json()


def _get_all_joined_teams(access_token: str) -> list[dict]:
    """Fetch ALL joined teams, handling @odata.nextLink pagination."""
    url = f"{GRAPH_BASE}/me/joinedTeams"
    teams: list[dict] = []

    while url:
        data = _graph_get(url, access_token)
        teams.extend(data.get("value", []))
        url = data.get("@odata.nextLink")  # None when no more pages

    log.info("Fetched %d joined teams total.", len(teams))
    return teams


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


def _get_team_drives(team_id: str, access_token: str) -> list[dict]:
    """Get all SharePoint drives for a team via its group site."""
    try:
        site = _graph_get(
            f"{GRAPH_BASE}/groups/{team_id}/sites/root", access_token
        )
    except GraphAPIError as exc:
        log.warning("Could not get site for team %s: %s", team_id, exc)
        return []

    site_id = site.get("id", "")
    if not site_id:
        return []

    try:
        drives_data = _graph_get(
            f"{GRAPH_BASE}/sites/{site_id}/drives", access_token
        )
    except GraphAPIError as exc:
        log.warning("Could not list drives for site %s: %s", site_id, exc)
        return []

    return drives_data.get("value", [])


def _search_drive_for_mp4(
    drive_id: str, access_token: str
) -> list[dict]:
    """Search a single drive for .mp4 files. Returns list of item dicts."""
    try:
        data = _graph_get(
            f"{GRAPH_BASE}/drives/{drive_id}/root/search(q='.mp4')",
            access_token,
        )
    except GraphAPIError as exc:
        log.warning("Search failed for drive %s: %s", drive_id, exc)
        return []

    return [
        item for item in data.get("value", [])
        if item.get("name", "").lower().endswith(".mp4")
    ]

# ───────────────────────── main entry point ───────────────────────

def fetch_recordings(
    access_token: str,
    subjects_path: str = "subjects_config.json",
    state_dir: str = ".state",
    subject_filter: str | None = None,
) -> dict[str, list[dict]]:
    """Scan Teams drives and return new recordings per subject.

    Parameters
    ----------
    access_token : str
        Valid Graph API Bearer token (from token_manager).
    subjects_path : str
        Path to subjects_config.json.
    state_dir : str
        Directory for per-subject last_run files.
    subject_filter : str | None
        If provided, only scan this one subject (by name or short name).
        If None, scan all 6 subjects ("Check All" mode).

    Returns
    -------
    dict mapping subject name → list of recording dicts, each with:
        - name: str           (filename)
        - size_mb: float      (size in MB, rounded to 1 decimal)
        - created: str        (ISO 8601 creation date)
        - drive_id: str       (for download in Phase 4)
        - item_id: str        (for download in Phase 4)
        - team_name: str      (team where recording was found)
    """
    subjects = load_subjects(subjects_path)

    # Optionally filter to a single subject
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

    # Fetch all joined teams once (shared across subjects)
    all_teams = _get_all_joined_teams(access_token)

    results: dict[str, list[dict]] = {}

    for subject in subjects:
        subj_name = subject["name"]
        last_run = get_last_run(state_dir, subj_name)
        matched_teams = _match_teams_to_subject(all_teams, subject)

        log.info(
            "Subject '%s': %d matching teams, last_run=%s",
            subj_name, len(matched_teams), last_run.isoformat(),
        )

        recordings: list[dict] = []
        seen_ids: set[str] = set()  # deduplicate across drives

        for team in matched_teams:
            team_name = team["displayName"]
            team_id = team["id"]
            drives = _get_team_drives(team_id, access_token)

            for drive in drives:
                items = _search_drive_for_mp4(drive["id"], access_token)
                for item in items:
                    item_id = item["id"]
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    # Parse creation date and apply date filter
                    created_str = item.get("createdDateTime", "")
                    try:
                        created_dt = datetime.fromisoformat(
                            created_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        continue  # skip items with unparseable dates

                    if created_dt <= last_run:
                        continue  # already seen in a previous run

                    size_bytes = item.get("size", 0)
                    recordings.append({
                        "name": item["name"],
                        "size_mb": round(size_bytes / (1024 * 1024), 1),
                        "created": created_str[:10],  # YYYY-MM-DD
                        "drive_id": drive["id"],
                        "item_id": item_id,
                        "team_name": team_name,
                    })

        # Sort by creation date, newest first
        recordings.sort(key=lambda r: r["created"], reverse=True)
        results[subj_name] = recordings

        log.info(
            "Subject '%s': found %d new recording(s).",
            subj_name, len(recordings),
        )

    return results
