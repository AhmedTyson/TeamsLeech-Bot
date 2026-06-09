import logging
from typing import Any

import httpx

from teamsleech.core.constants import GRAPH_BASE_URL

log = logging.getLogger("graph_api")

class GraphAPIError(Exception):
    pass

class GraphClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        limits = httpx.Limits(
            max_connections=20, max_keepalive_connections=10
        )
        self.client = httpx.AsyncClient(limits=limits, timeout=30.0)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    async def get(
        self,
        endpoint_or_url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = (
            endpoint_or_url
            if endpoint_or_url.startswith("http")
            else f"{GRAPH_BASE_URL}{endpoint_or_url}"
        )

        try:
            resp = await self.client.get(
                url, headers=self.headers, params=params
            )
        except httpx.RequestError as exc:
            raise GraphAPIError(f"Network error: {exc}") from exc

        if resp.status_code != 200:
            raise GraphAPIError(
                f"Graph API GET error [{resp.status_code}]:"
                f" {resp.text[:300]}"
            )

        return resp.json()

    async def post(
        self, endpoint_or_url: str, json_data: dict[str, Any]
    ) -> dict[str, Any]:
        url = (
            endpoint_or_url
            if endpoint_or_url.startswith("http")
            else f"{GRAPH_BASE_URL}{endpoint_or_url}"
        )

        try:
            resp = await self.client.post(
                url, headers=self.headers, json=json_data
            )
        except httpx.RequestError as exc:
            raise GraphAPIError(f"Network error: {exc}") from exc

        if resp.status_code not in (200, 201, 202, 204):
            raise GraphAPIError(
                f"Graph API POST error [{resp.status_code}]:"
                f" {resp.text[:300]}"
            )

        return resp.json() if resp.status_code != 204 else {}

    async def get_all_pages(
        self, endpoint: str
    ) -> list[dict[str, Any]]:
        items = []
        next_link = (
            endpoint
            if endpoint.startswith("http")
            else f"{GRAPH_BASE_URL}{endpoint}"
        )

        while next_link:
            page_data = await self.get(next_link)
            items.extend(page_data.get("value", []))
            next_link = page_data.get("@odata.nextLink")

        return items

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
