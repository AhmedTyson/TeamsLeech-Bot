import logging
from typing import List, Tuple

from teamsleech.models.domain import Team
from teamsleech.services.graph import GraphClient

log = logging.getLogger("discovery")

class DiscoveryService:
    """
    Handles finding and searching through the user's joined Teams.
    """
    def __init__(self, graph_client: GraphClient):
        self.graph = graph_client

    async def get_all_joined_teams(self) -> List[Team]:
        """Fetch all joined teams via Graph API and map to Pydantic models."""
        log.info("Fetching all joined teams from Microsoft Graph...")
        raw_teams = await self.graph.get_all_pages("/me/joinedTeams")
        return [Team(**team) for team in raw_teams]

    async def search_teams(self, keyword: str) -> Tuple[bool, str, List[Team]]:
        """
        Smart Search Engine for Teams.
        
        Returns:
            Tuple[bool, str, List[Team]]: 
                - bool: True if valid search, False if invalid
                - str: Error message or Success message
                - List[Team]: Matched teams
        """
        keyword = keyword.strip().lower()
        
        if len(keyword) < 3:
            return False, f"⚠️ The keyword '{keyword}' is too short. Please provide at least 3 characters to search.", []

        all_teams = await self.get_all_joined_teams()
        
        # Filter teams based on keyword match
        matched_teams = [
            team for team in all_teams 
            if keyword in team.display_name.lower()
        ]
        
        if not matched_teams:
            return True, f"🔍 No teams found matching '{keyword}'.", []
            
        return True, f"🔍 Found {len(matched_teams)} team(s) matching '{keyword}'.", matched_teams
