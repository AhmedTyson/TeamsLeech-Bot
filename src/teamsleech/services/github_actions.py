import logging

import httpx

from teamsleech.core.config import settings
from teamsleech.core.retry import retry_http

log = logging.getLogger("github_actions")

GH_API_BASE = "https://api.github.com"
GH_TIMEOUT = 15.0

def _get_headers() -> dict[str, str]:
    if not settings.gh_pat:
        raise ValueError("GH_PAT is not configured.")
    return {
        "Authorization": f"Bearer {settings.gh_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

@retry_http
async def trigger_workflow(workflow_id: str = "bot-runner.yml", ref: str = "main") -> None:
    if not settings.github_repository:
        raise ValueError("GITHUB_REPOSITORY is not configured.")
        
    url = f"{GH_API_BASE}/repos/{settings.github_repository}/actions/workflows/{workflow_id}/dispatches"
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, 
            headers=_get_headers(), 
            json={"ref": ref}, 
            timeout=GH_TIMEOUT
        )
        resp.raise_for_status()

@retry_http
async def get_active_runs() -> list[dict]:
    if not settings.github_repository:
        raise ValueError("GITHUB_REPOSITORY is not configured.")
        
    url = f"{GH_API_BASE}/repos/{settings.github_repository}/actions/runs"
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url, 
            headers=_get_headers(), 
            params={"per_page": 20}, 
            timeout=GH_TIMEOUT
        )
        resp.raise_for_status()
        runs = resp.json().get("workflow_runs", [])
        
        # Filter for runs that are not completed (captures queued, in_progress, requested, pending)
        return [r for r in runs if r.get("status") != "completed"]

@retry_http
async def cancel_run(run_id: int) -> None:
    if not settings.github_repository:
        raise ValueError("GITHUB_REPOSITORY is not configured.")
        
    url = f"{GH_API_BASE}/repos/{settings.github_repository}/actions/runs/{run_id}/cancel"
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, 
            headers=_get_headers(), 
            timeout=GH_TIMEOUT
        )
        resp.raise_for_status()
