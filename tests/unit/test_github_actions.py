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


@pytest.fixture
def mock_settings():
    with patch("teamsleech.services.github_actions.settings") as mock_settings_module:
        mock_settings_module.gh_pat = "fake_pat"
        mock_settings_module.github_repository = "fake/repo"
        yield mock_settings_module

def test_get_headers_success(mock_settings):
    headers = _get_headers()
    assert headers["Authorization"] == "Bearer fake_pat"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"

def test_get_headers_missing_pat(mock_settings):
    mock_settings.gh_pat = ""
    with pytest.raises(ValueError, match="GH_PAT is not configured."):
        _get_headers()

@pytest.mark.asyncio
async def test_trigger_workflow_success(respx_mock, mock_settings):
    url = f"{GH_API_BASE}/repos/fake/repo/actions/workflows/bot-runner.yml/dispatches"
    route = respx_mock.post(url).mock(return_value=httpx.Response(204))
    
    await trigger_workflow()
    
    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer fake_pat"
    import json
    assert json.loads(request.content) == {"ref": "main"}

@pytest.mark.asyncio
async def test_trigger_workflow_missing_repo(mock_settings):
    mock_settings.github_repository = ""
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY is not configured."):
        await trigger_workflow()

@pytest.mark.asyncio
async def test_get_active_runs_success(respx_mock, mock_settings):
    url = f"{GH_API_BASE}/repos/fake/repo/actions/runs"
    
    respx_mock.get(url, params={"status": "in_progress"}).mock(
        return_value=httpx.Response(200, json={"workflow_runs": [{"id": 1, "status": "in_progress", "name": "Test1"}]})
    )
    respx_mock.get(url, params={"status": "queued"}).mock(
        return_value=httpx.Response(200, json={"workflow_runs": [{"id": 2, "status": "queued", "name": "Test2"}]})
    )
    
    runs = await get_active_runs()
    
    assert len(runs) == 2
    assert runs[0]["id"] == 1
    assert runs[1]["id"] == 2

@pytest.mark.asyncio
async def test_get_active_runs_missing_repo(mock_settings):
    mock_settings.github_repository = ""
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY is not configured."):
        await get_active_runs()

@pytest.mark.asyncio
async def test_cancel_run_success(respx_mock, mock_settings):
    run_id = 123
    url = f"{GH_API_BASE}/repos/fake/repo/actions/runs/{run_id}/cancel"
    route = respx_mock.post(url).mock(return_value=httpx.Response(202))
    
    await cancel_run(run_id)
    
    assert route.called

@pytest.mark.asyncio
async def test_cancel_run_missing_repo(mock_settings):
    mock_settings.github_repository = ""
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY is not configured."):
        await cancel_run(123)
