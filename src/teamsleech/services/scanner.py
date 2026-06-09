import asyncio
from datetime import datetime, timezone
import json
import logging
import re

from teamsleech.core.config import settings
from teamsleech.core.constants import MAX_CONCURRENT_SEARCHES
from teamsleech.models.domain import SubjectConfig, Recording, Team
from teamsleech.services.graph import GraphClient, GraphAPIError
from teamsleech.services.state import StateManager

log = logging.getLogger("scanner")

class ScannerService:
    def __init__(self, graph_client: GraphClient, state_manager: StateManager):
        self.graph = graph_client
        self.state = state_manager

    def load_subjects(self) -> list[SubjectConfig]:
        if settings.subjects_json:
            try:
                data = json.loads(settings.subjects_json)
                return [SubjectConfig(**s) for s in data.get("subjects", [])]
            except Exception as e:
                log.error("Failed to parse SUBJECTS_JSON env var: %s", e)

        try:
            with open(settings.subjects_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [SubjectConfig(**s) for s in data.get("subjects", [])]
        except Exception as e:
            log.error("Failed to read subjects file: %s", e)
            return []

    def _match_teams(
        self, all_teams: list[Team], subject: SubjectConfig
    ) -> list[Team]:
        matched = []
        keywords = [kw.lower() for kw in subject.keywords]

        for team in all_teams:
            name_lower = team.display_name.lower()
            for kw in keywords:
                if kw.isalpha():
                    if re.search(rf"\b{re.escape(kw)}\b", name_lower):
                        matched.append(team)
                        break
                else:
                    if kw in name_lower:
                        matched.append(team)
                        break
        return matched

    async def _process_team(
        self,
        team: Team,
        subject: SubjectConfig,
        last_run: datetime,
        date_start: str | None,
        date_end: str | None,
        seen_ids: set[str],
    ) -> list[Recording]:
        recordings = []

        try:
            site = await self.graph.get(f"/groups/{team.id}/sites/root")
            site_id = site.get("id")
            if not site_id:
                return []
        except GraphAPIError as e:
            log.warning(
                "Could not get site for team %s: %s",
                team.display_name, e,
            )
            return []

        try:
            drives_data = await self.graph.get(
                f"/sites/{site_id}/drives"
            )
            drives = drives_data.get("value", [])
        except GraphAPIError as e:
            log.warning(
                "Could not list drives for site %s: %s", site_id, e
            )
            return []

        async def search_drive(drive_id: str):
            extensions = [
                ".mp4", ".pdf", ".pptx", ".ppt",
                ".docx", ".doc", ".xlsx", ".zip", ".rar",
            ]
            tasks = [
                self.graph.get(
                    f"/drives/{drive_id}/root/search(q='{ext}')"
                )
                for ext in extensions
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            items = []
            for ext, res in zip(extensions, results):
                if not isinstance(res, Exception):
                    for i in res.get("value", []):
                        name = i.get("name", "").lower()
                        if name.endswith(ext):
                            items.append(i)
            return drive_id, items

        drive_tasks = [search_drive(d["id"]) for d in drives]
        drive_results = await asyncio.gather(*drive_tasks)

        for drive_id, items in drive_results:
            for item in items:
                item_id = item["id"]
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                created_str = item.get("createdDateTime", "")
                created_date_only = created_str[:10]
                time_only = (
                    created_str[11:16] if len(created_str) >= 16 else ""
                )

                if date_start:
                    if date_end:
                        if not (
                            date_start <= created_date_only <= date_end
                        ):
                            continue
                    else:
                        if created_date_only != date_start:
                            continue
                else:
                    try:
                        created_dt = datetime.fromisoformat(
                            created_str.replace("Z", "+00:00")
                        )
                        if created_dt <= last_run:
                            continue
                    except ValueError:
                        continue

                size_bytes = item.get("size", 0)
                duration_ms = item.get("video", {}).get("duration", 0)
                is_video = (
                    item.get("name", "").lower().endswith(".mp4")
                )

                recordings.append(
                    Recording(
                        name=item["name"],
                        size_mb=round(size_bytes / (1024 * 1024), 1),
                        created=created_date_only,
                        time=time_only,
                        duration_ms=duration_ms,
                        drive_id=drive_id,
                        item_id=item_id,
                        team_name=team.display_name,
                        subject_name=subject.name,
                        is_video=is_video,
                    )
                )

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
                if s.name.lower() == filter_lower
                or s.short.lower() == filter_lower
            ]
            if not subjects:
                raise ValueError(
                    f"No subject matches filter '{subject_filter}'."
                )

        results: dict[str, list[Recording]] = {}

        from teamsleech.services.discovery import DiscoveryService

        discovery = DiscoveryService(self.graph)
        all_teams = await discovery.get_all_joined_teams()

        for subject in subjects:
            try:
                last_run = self.state.get_last_run(subject.name)
                matched_teams = self._match_teams(all_teams, subject)
                seen_ids: set[str] = set()

                log.info(
                    "Scanning '%s': %d teams. Since: %s",
                    subject.name,
                    len(matched_teams),
                    last_run,
                )

                sem = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)

                async def bounded_process(
                    team: Team,
                    _subject=subject,
                    _last_run=last_run,
                    _date_start=date_start,
                    _date_end=date_end,
                    _seen_ids=seen_ids,
                ):
                    async with sem:
                        return await self._process_team(
                            team,
                            _subject,
                            _last_run,
                            _date_start,
                            _date_end,
                            _seen_ids,
                        )

                tasks = [bounded_process(t) for t in matched_teams]
                team_results = await asyncio.gather(*tasks)

                recordings = [
                    r for batch in team_results for r in batch
                ]
                recordings.sort(key=lambda r: r.created, reverse=True)
                results[subject.name] = recordings

                if recordings:
                    latest = max(r.created for r in recordings)
                    try:
                        timestamp = datetime.fromisoformat(
                            f"{latest}T23:59:59+00:00"
                        )
                        await self.state.save_last_run(
                            subject.name, timestamp
                        )
                    except Exception:
                        pass
                log.info(
                    "'%s' scan complete: %d recordings found.",
                    subject.name,
                    len(recordings),
                )
            except Exception as e:
                log.error(
                    "Scan failed for subject '%s': %s",
                    subject.name, e,
                )
                results[subject.name] = []

        return results
