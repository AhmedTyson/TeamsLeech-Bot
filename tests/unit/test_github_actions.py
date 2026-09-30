import json
from unittest.mock import patch

import httpx
import pytest

from teamsleech.services.github_actions import (
    GH_API_BASE,
    _get_headers,
    cancel_run,
    get_active_runs,
    trigger_workflow,
)


def _resp(status, payload=None):
    if payload is not None:
        return httpx.Response(status, json=payload)
    return httpx.Response(status)


@pytest.fixture
def mock_settings():
    with patch("teamsleech.services.github_actions.settings") as mock_module:
        mock_module.gh_pat = "fake_pat"
        mock_module.github_repository = "fake/repo"
        yield mock_module


def test_get_headers_success(mock_settings):
    headers = _get_headers()
    assert headers["Authorization"] == "Bearer fake_pat"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_get_headers_missing_pat(mock_settings):
    mock_settings.gh_pat = ""
    with pytest.raises(ValueError, match="GH_PAT is not configured."):
        _get_headers()


async def test_trigger_workflow_success(mock_github_api, mock_settings):
    url = f"{GH_API_BASE}/repos/fake/repo/actions/workflows/bot-runner.yml/dispatches"
    route = mock_github_api.post(url).mock(return_value=_resp(204))

    await trigger_workflow()

    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer fake_pat"
    assert json.loads(request.content) == {"ref": "main"}


async def test_trigger_workflow_missing_repo(mock_settings):
    mock_settings.github_repository = ""
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY is not configured."):
        await trigger_workflow()


async def test_get_active_runs_success(mock_github_api, mock_settings):
    url = f"{GH_API_BASE}/repos/fake/repo/actions/runs"

    mock_github_api.get(url, params={"per_page": "20"}).mock(
        return_value=_resp(
            200,
            {
                "workflow_runs": [
                    {"id": 1, "status": "in_progress", "name": "Test1"},
                    {"id": 2, "status": "queued", "name": "Test2"},
                    {"id": 3, "status": "completed", "name": "Test3"},
                ]
            },
        )
    )

    runs = await get_active_runs()

    assert len(runs) == 2
    assert runs[0]["id"] == 1
    assert runs[1]["id"] == 2


async def test_get_active_runs_missing_repo(mock_settings):
    mock_settings.github_repository = ""
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY is not configured."):
        await get_active_runs()


async def test_cancel_run_success(mock_github_api, mock_settings):
    run_id = 123
    url = f"{GH_API_BASE}/repos/fake/repo/actions/runs/{run_id}/cancel"
    route = mock_github_api.post(url).mock(return_value=_resp(202))

    await cancel_run(run_id)

    assert route.called


async def test_cancel_run_missing_repo(mock_settings):
    mock_settings.github_repository = ""
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY is not configured."):
        await cancel_run(123)
