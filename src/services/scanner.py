import json
import logging
import asyncio
import re
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional

from core.config import settings
from core.constants import MAX_CONCURRENT_SEARCHES
from models.domain import SubjectConfig, Recording, Team
from services.graph import GraphClient, GraphAPIError
from services.state import StateManager

log = logging.getLogger("scanner")

class ScannerService:
    """
    Business Logic for finding Microsoft Teams lecture recordings.
    """
    def __init__(self, graph_client: GraphClient, state_manager: StateManager):
        self.graph = graph_client
        self.state = state_manager

    def load_subjects(self) -> List[SubjectConfig]:
        """Loads subject configuration from JSON or env vars into Pydantic models."""
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

    def _match_teams(self, all_teams: List[Team], subject: SubjectConfig) -> List[Team]:
        """Filter teams whose displayName contains any of the subject's keywords."""
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
        date_start: Optional[str],
        date_end: Optional[str],
        seen_ids: Set[str]
    ) -> List[Recording]:
        """Fetch drives and search .mp4s for one specific team."""
        recordings = []

        # 1. Get Site ID
        try:
            site = await self.graph.get(f"/groups/{team.id}/sites/root")
            site_id = site.get("id")
            if not site_id: return []
        except GraphAPIError as e:
            log.warning("Could not get site for team %s: %s", team.display_name, e)
            return []

        # 2. Get Drives
        try:
            drives_data = await self.graph.get(f"/sites/{site_id}/drives")
            drives = drives_data.get("value", [])
        except GraphAPIError as e:
            log.warning("Could not list drives for site %s: %s", site_id, e)
            return []

        # 3. Search Drives Concurrently
        async def search_drive(drive_id: str):
            try:
                # Fire both .mp4 and .pdf searches concurrently
                task_mp4 = self.graph.get(f"/drives/{drive_id}/root/search(q='.mp4')")
                task_pdf = self.graph.get(f"/drives/{drive_id}/root/search(q='.pdf')")
                res_mp4, res_pdf = await asyncio.gather(task_mp4, task_pdf, return_exceptions=True)
                
                items = []
                if not isinstance(res_mp4, Exception):
                    items.extend([i for i in res_mp4.get("value", []) if i.get("name", "").lower().endswith(".mp4")])
                if not isinstance(res_pdf, Exception):
                    items.extend([i for i in res_pdf.get("value", []) if i.get("name", "").lower().endswith(".pdf")])
                    
                return drive_id, items
            except Exception:
                return drive_id, []

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
                time_only = created_str[11:16] if len(created_str) >= 16 else ""

                # Filtering Logic
                if date_start:
                    if date_end:
                        if not (date_start <= created_date_only <= date_end):
                            continue
                    else:
                        if created_date_only != date_start:
                            continue
                else:
                    try:
                        created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                        if created_dt <= last_run:
                            continue
                    except ValueError:
                        continue

                size_bytes = item.get("size", 0)
                duration_ms = item.get("video", {}).get("duration", 0)
                is_pdf = item.get("name", "").lower().endswith(".pdf")

                recordings.append(Recording(
                    name=item["name"],
                    size_mb=round(size_bytes / (1024 * 1024), 1),
                    created=created_date_only,
                    time=time_only,
                    duration_ms=duration_ms,
                    drive_id=drive_id,
                    item_id=item_id,
                    team_name=team.display_name,
                    subject_name=subject.name,
                    is_pdf=is_pdf
                ))

        return recordings

    async def scan_recordings(
        self,
        subject_filter: Optional[str] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None
    ) -> Dict[str, List[Recording]]:
        """
        Orchestrates concurrent searches across all subjects and teams.
        """
        subjects = self.load_subjects()
        
        if subject_filter:
            filter_lower = subject_filter.lower()
            subjects = [
                s for s in subjects 
                if s.name.lower() == filter_lower or s.short.lower() == filter_lower
            ]
            if not subjects:
                raise ValueError(f"No subject matches filter '{subject_filter}'.")

        results: Dict[str, List[Recording]] = {}
        
        # We need Team models. We can fetch them via graph directly.
        from services.discovery import DiscoveryService
        discovery = DiscoveryService(self.graph)
        all_teams = await discovery.get_all_joined_teams()

        for subject in subjects:
            last_run = self.state.get_last_run(subject.name)
            matched_teams = self._match_teams(all_teams, subject)
            seen_ids: Set[str] = set()

            log.info("Scanning '%s': %d teams. Since: %s", subject.name, len(matched_teams), last_run)

            # Limit concurrency to avoid hitting Graph API rate limits too hard
            sem = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)
            
            async def bounded_process(team: Team):
                async with sem:
                    return await self._process_team(team, subject, last_run, date_start, date_end, seen_ids)

            tasks = [bounded_process(t) for t in matched_teams]
            team_results = await asyncio.gather(*tasks)

            # Flatten and sort
            recordings = [r for batch in team_results for r in batch]
            recordings.sort(key=lambda r: r.created, reverse=True)
            results[subject.name] = recordings

        return results
