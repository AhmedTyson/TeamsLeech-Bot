import logging

from teamsleech.models.domain import Team
from teamsleech.services.graph import GraphClient

log = logging.getLogger("discovery")

class DiscoveryService:
    def __init__(self, graph_client: GraphClient):
        self.graph = graph_client

    async def get_all_joined_teams(self) -> list[Team]:
        log.info("Fetching all joined teams from Microsoft Graph...")
        raw_teams = await self.graph.get_all_pages("/me/joinedTeams")
        return [Team(**team) for team in raw_teams]

    async def search_teams(
        self, keyword: str
    ) -> tuple[bool, str, list[Team]]:
        keyword = keyword.strip().lower()

        if len(keyword) < 3:
            return (
                False,
                f"⚠️ The keyword '{keyword}' is too short."
                " Please provide at least 3 characters to search.",
                [],
            )

        all_teams = await self.get_all_joined_teams()

        matched_teams = [
            team
            for team in all_teams
            if keyword in team.display_name.lower()
        ]

        if not matched_teams:
            return (
                True,
                f"🔍 No teams found matching '{keyword}'.",
                [],
            )

        return (
            True,
            f"🔍 Found {len(matched_teams)} team(s) matching '{keyword}'.",
            matched_teams,
        )
