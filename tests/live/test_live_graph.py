"""Live smoke tests against real Microsoft Graph + Telegram.

NOT run in CI. Run locally only with real credentials::

    $env:LIVE_TEST = "1"
    $env:TEAMS_REFRESH_TOKEN = "..."
    $env:TELEGRAM_API_ID = "..."
    ... (see .env.example)
    uv run --python 3.11 pytest tests/live -q -p no:cacheprovider --no-cov

WARNING: ``test_live_authenticate`` rotates TEAMS_REFRESH_TOKEN by design
(kept in-process + GitHub secret). Read-only otherwise: no uploads,
no state pushes.
"""

import os

import pytest

LIVE = os.getenv("LIVE_TEST") == "1"

REQUIRED = [
    "TEAMS_REFRESH_TOKEN",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]


def _require_live(monkeypatch):
    if not LIVE:
        pytest.skip("live test: set LIVE_TEST=1 with real creds")
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        pytest.skip(f"live test: missing env {missing}")
    from teamsleech.core.config import settings

    mapping = {
        "teams_refresh_token": "TEAMS_REFRESH_TOKEN",
        "teams_client_id": "TEAMS_CLIENT_ID",
        "telegram_api_id": "TELEGRAM_API_ID",
        "telegram_api_hash": "TELEGRAM_API_HASH",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
        "telegram_chat_id": "TELEGRAM_CHAT_ID",
        "gh_pat": "GH_PAT",
        "github_repository": "GITHUB_REPOSITORY",
    }
    for attr, env in mapping.items():
        if os.environ.get(env) is not None:
            monkeypatch.setattr(settings, attr, os.environ[env])


async def test_live_authenticate(monkeypatch):
    _require_live(monkeypatch)
    from teamsleech.services.auth import authenticate

    token = await authenticate()
    assert isinstance(token, str) and len(token) > 10


async def test_live_list_joined_teams(monkeypatch):
    _require_live(monkeypatch)
    from teamsleech.services.auth import authenticate
    from teamsleech.services.discovery import DiscoveryService
    from teamsleech.services.graph import GraphClient

    token = await authenticate()
    async with GraphClient(token) as graph:
        teams = await DiscoveryService(graph).get_all_joined_teams()
    assert isinstance(teams, list)
    print(f"\nJoined teams ({len(teams)}): {[t.display_name for t in teams]}")
