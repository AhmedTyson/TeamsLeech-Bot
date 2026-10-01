from unittest.mock import AsyncMock

from teamsleech.models.domain import Team
from teamsleech.services.discovery import DiscoveryService


def _svc(teams):
    from unittest.mock import MagicMock

    graph = MagicMock()
    graph.get_all_pages = AsyncMock(return_value=teams)
    return DiscoveryService(graph)


async def test_get_all_joined_teams_maps_models():
    svc = _svc([{"id": "t1", "displayName": "Math Group"}])
    result = await svc.get_all_joined_teams()
    assert result == [Team(id="t1", displayName="Math Group")]


async def test_search_rejects_short_keyword():
    svc = _svc([])
    ok, msg, teams = await svc.search_teams("ab")
    assert ok is False
    assert teams == []
    assert "at least 3" in msg


async def test_search_no_match():
    svc = _svc([{"id": "t1", "displayName": "Math Group"}])
    ok, msg, teams = await svc.search_teams("physics")
    assert ok is True
    assert teams == []
    assert "No teams found" in msg


async def test_search_match_case_insensitive():
    svc = _svc([{"id": "t1", "displayName": "Math Group"}])
    ok, msg, teams = await svc.search_teams("  MATH ")
    assert ok is True
    assert [t.id for t in teams] == ["t1"]
    assert "1 team(s)" in msg
