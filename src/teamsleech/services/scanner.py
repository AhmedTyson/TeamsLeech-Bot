import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, cast

from teamsleech.core.config import settings
from teamsleech.core.constants import MAX_CONCURRENT_SEARCHES
from teamsleech.models.domain import Recording, SubjectConfig, Team
from teamsleech.services.graph import GraphAPIError, GraphClient, quote_id
from teamsleech.services.state import StateManager

log = logging.getLogger("scanner")

EXTENSIONS = [
    ".mp4",
    ".pdf",
    ".pptx",
    ".ppt",
    ".docx",
    ".doc",
    ".xlsx",
    ".zip",
    ".rar",
]


class ScannerService:
    def __init__(self, graph_client: GraphClient, state_manager: StateManager):
        self.graph = graph_client
        self.state = state_manager

    def load_subjects(self) -> list[SubjectConfig]:
        if settings.subjects_json:
            try:
                data = json.loads(settings.subjects_json)
                return [SubjectConfig(**s) for s in data.get("subjects", [])]
            except Exception:
                log.exception("Failed to parse SUBJECTS_JSON env var")

        try:
            with open(settings.subjects_path, encoding="utf-8") as f:
                data = json.load(f)
            return [SubjectConfig(**s) for s in data.get("subjects", [])]
        except Exception:
            log.exception("Failed to read subjects file")
            return []

    def _match_teams(self, all_teams: list[Team], subject: SubjectConfig) -> list[Team]:
        matched = []
        keywords = [
            re.sub(r"\s+", " ", kw.strip().lower()) for kw in subject.keywords if kw.strip()
        ]

        for team in all_teams:
            name = re.sub(r"\s+", " ", team.display_name.strip().lower())
            for kw in keywords:
                # Word-start match. Short keywords (<3 chars) require a
                # full word so "cs" matches "CS 101" but not "cs101".
                pattern = rf"\b{re.escape(kw)}"
                if len(kw) < 3:
                    pattern += r"\b"
                if re.search(pattern, name):
                    matched.append(team)
                    break
        return matched

    @staticmethod
    def _parse_item_datetime(item: dict[str, Any]) -> datetime | None:
        created_str = item.get("createdDateTime", "")
        try:
            created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        except ValueError:
            log.warning(
                "Skipping item with bad createdDateTime %r: %s",
                created_str,
                item.get("name"),
            )
            return None
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=UTC)
        return created_dt

    @staticmethod
    def _item_to_recording(
        item: dict[str, Any],
        drive_id: str,
        team: Team,
        subject: SubjectConfig,
        created_dt: datetime,
    ) -> Recording | None:
        size_bytes = item.get("size") or 0
        try:
            size_mb = round(size_bytes / (1024 * 1024), 1)
        except TypeError:
            log.warning(
                "Skipping item with bad size %r: %s",
                item.get("size"),
                item.get("name"),
            )
            return None
        duration_ms = (item.get("video") or {}).get("duration", 0)
        return Recording(
            name=item["name"],
            size_mb=size_mb,
            created=created_dt.date().isoformat(),
            time=created_dt.strftime("%H:%M"),
            duration_ms=duration_ms,
            drive_id=drive_id,
            item_id=item["id"],
            team_name=team.display_name,
            subject_name=subject.name,
            is_video=item.get("name", "").lower().endswith(".mp4"),
        )

    async def _search_drives(
        self,
        drives: list[dict[str, Any]],
        team: Team,
        sem: asyncio.Semaphore,
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        async def search_once(drive_id: str, ext: str) -> dict[str, Any]:
            # OData string escape ('' for ') + URL-encode the drive id.
            query = ext.replace("'", "''")
            async with sem:
                return await self.graph.get(
                    f"/drives/{quote_id(drive_id)}/root/search(q='{query}')"
                )

        async def search_drive(drive_id: str) -> tuple[str, list[dict[str, Any]]]:
            tasks = [search_once(drive_id, ext) for ext in EXTENSIONS]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            items: list[dict[str, Any]] = []
            for ext, res in zip(EXTENSIONS, results, strict=True):
                if isinstance(res, BaseException):
                    log.warning(
                        "Drive search failed (team=%s drive=%s ext=%s): %s",
                        team.display_name,
                        drive_id,
                        ext,
                        res,
                    )
                    continue
                for i in res.get("value", []):
                    name = i.get("name", "").lower()
                    if name.endswith(ext):
                        items.append(i)
            return drive_id, items

        drive_tasks = [search_drive(d["id"]) for d in drives]
        return cast(
            "list[tuple[str, list[dict[str, Any]]]]",
            await asyncio.gather(*drive_tasks),
        )

    @staticmethod
    def _passes_date_filter(
        created_dt: datetime,
        date_start: str | None,
        date_end: str | None,
        last_run: datetime,
    ) -> bool:
        if date_start:
            day = created_dt.date().isoformat()
            if date_end:
                return date_start <= day <= date_end
            return day == date_start
        return created_dt > last_run

    async def _resolve_team_drives(self, team: Team) -> list[dict[str, Any]]:
        """Site + drive listing for a team; [] when unavailable."""
        try:
            site = await self.graph.get(f"/groups/{quote_id(team.id)}/sites/root")
        except GraphAPIError as e:
            log.warning(
                "Could not get site for team %s: %s",
                team.display_name,
                e,
            )
            return []
        site_id = site.get("id")
        if not site_id:
            return []
        try:
            drives_data = await self.graph.get(f"/sites/{quote_id(site_id)}/drives")
        except GraphAPIError as e:
            log.warning("Could not list drives for site %s: %s", site_id, e)
            return []
        return cast("list[dict[str, Any]]", drives_data.get("value", []))

    async def _process_team(
        self,
        team: Team,
        subject: SubjectConfig,
        last_run: datetime,
        date_start: str | None,
        date_end: str | None,
        seen_ids: set[str],
        search_sem: asyncio.Semaphore | None = None,
    ) -> list[Recording]:
        recordings = []
        # Snapshot shared ids; cross-team dupes are filtered in
        # scan_recordings so concurrent teams never race on one set.
        local_seen = set(seen_ids)

        drives = await self._resolve_team_drives(team)
        if not drives:
            return []

        sem = search_sem or asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)
        drive_results = await self._search_drives(drives, team, sem)

        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=UTC)

        for drive_id, items in drive_results:
            for item in items:
                item_id = item["id"]
                if item_id in local_seen:
                    continue
                local_seen.add(item_id)

                created_dt = self._parse_item_datetime(item)
                if created_dt is None:
                    continue
                if not self._passes_date_filter(created_dt, date_start, date_end, last_run):
                    continue

                rec = self._item_to_recording(item, drive_id, team, subject, created_dt)
                if rec is not None:
                    recordings.append(rec)

        seen_ids.update(local_seen)
        return recordings

    async def _scan_subject(
        self,
        subject: SubjectConfig,
        all_teams: list[Team],
        date_start: str | None,
        date_end: str | None,
    ) -> list[Recording]:
        last_run = self.state.get_last_run(subject.name)
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=UTC)
        matched_teams = self._match_teams(all_teams, subject)
        seen_ids: set[str] = set()

        log.info(
            "Scanning '%s': %d teams. Since: %s",
            subject.name,
            len(matched_teams),
            last_run,
        )

        team_sem = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)
        search_sem = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)

        async def bounded_process(
            team: Team,
            _team_sem: asyncio.Semaphore = team_sem,
            _search_sem: asyncio.Semaphore = search_sem,
            _subject: SubjectConfig = subject,
            _last_run: datetime = last_run,
            _date_start: str | None = date_start,
            _date_end: str | None = date_end,
            _seen_ids: set[str] = seen_ids,
        ) -> list[Recording]:
            async with _team_sem:
                return await self._process_team(
                    team,
                    _subject,
                    _last_run,
                    _date_start,
                    _date_end,
                    _seen_ids,
                    _search_sem,
                )

        tasks = [bounded_process(t) for t in matched_teams]
        team_results = await asyncio.gather(*tasks)

        seen_keys: set[tuple[str, str]] = set()
        recordings: list[Recording] = []
        for batch in team_results:
            for r in batch:
                key = (r.drive_id, r.item_id)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                recordings.append(r)
        recordings.sort(key=lambda r: r.created, reverse=True)
        return recordings

    async def scan_recordings(
        self,
        subject_filter: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> dict[str, list[Recording]]:
        subjects = self.load_subjects()

        if subject_filter:
            filter_lower = subject_filter.lower()
            subjects = [
                s
                for s in subjects
                if s.name.lower() == filter_lower or s.short.lower() == filter_lower
            ]
            if not subjects:
                msg = f"No subject matches filter '{subject_filter}'."
                raise ValueError(msg)

        results: dict[str, list[Recording]] = {}

        from teamsleech.services.discovery import DiscoveryService

        try:
            discovery = DiscoveryService(self.graph)
            all_teams = await discovery.get_all_joined_teams()
        except GraphAPIError:
            log.exception("Failed to fetch teams")
            return {s.name: [] for s in subjects}

        for subject in subjects:
            try:
                recordings = await self._scan_subject(subject, all_teams, date_start, date_end)
            except Exception:
                log.exception(
                    "Scan failed for subject '%s'",
                    subject.name,
                )
                results[subject.name] = []
            else:
                results[subject.name] = recordings
                log.info(
                    "'%s' scan complete: %d recordings found.",
                    subject.name,
                    len(recordings),
                )

        return results
