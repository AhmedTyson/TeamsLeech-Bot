import logging
from typing import Any, cast
from urllib.parse import quote, urlparse

import httpx

from teamsleech.core.constants import GRAPH_BASE_URL
from teamsleech.core.retry import (
    _http_status_error,
    honor_retry_after,
    retry_http,
)
from teamsleech.services.auth import TokenExpiredError

log = logging.getLogger("graph_api")

GRAPH_ALLOWED_HOSTS = {"graph.microsoft.com"}


def quote_id(raw: str | int) -> str:
    """URL-encode an API-supplied id for path interpolation.

    Keeps `!` (used by drive ids); everything else special is
    percent-encoded so ids cannot break out of the path.
    """
    return quote(str(raw), safe="!")


def _require_graph_url(url: str) -> str:
    host = urlparse(url).hostname
    if host not in GRAPH_ALLOWED_HOSTS:
        msg = f"Refusing non-Graph URL host: {host}"
        raise GraphAPIError(msg)
    return url


class GraphAPIError(Exception):
    pass


class GraphClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        self.client = httpx.AsyncClient(limits=limits, timeout=30.0)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    @retry_http
    async def _get_raw(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        resp = await self.client.get(url, headers=headers, params=params)
        if resp.status_code == 429 or resp.status_code >= 500:
            await honor_retry_after(resp)
            msg = f"Graph GET throttled [{resp.status_code}]"
            raise _http_status_error(msg, resp)
        return resp

    @retry_http
    async def _post_raw(
        self,
        url: str,
        headers: dict[str, str],
        json_data: dict[str, Any],
    ) -> httpx.Response:
        resp = await self.client.post(url, headers=headers, json=json_data)
        if resp.status_code == 429 or resp.status_code >= 500:
            await honor_retry_after(resp)
            msg = f"Graph POST throttled [{resp.status_code}]"
            raise _http_status_error(msg, resp)
        return resp

    async def get(
        self,
        endpoint_or_url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = _require_graph_url(
            endpoint_or_url
            if endpoint_or_url.startswith("http")
            else f"{GRAPH_BASE_URL}{endpoint_or_url}"
        )

        try:
            resp = await self._get_raw(url, self.headers, params=params)
        except httpx.HTTPStatusError as exc:
            msg = f"Graph API GET failed after retries: {exc}"
            raise GraphAPIError(msg) from exc
        except httpx.RequestError as exc:
            msg = f"Network error: {exc}"
            raise GraphAPIError(msg) from exc

        if resp.status_code == 401:
            msg = "Graph access token expired or revoked (401) — re-authenticate."
            raise TokenExpiredError(msg)
        if resp.status_code != 200:
            msg = f"Graph API GET error [{resp.status_code}]"
            raise GraphAPIError(msg)

        return cast("dict[str, Any]", resp.json())

    async def post(self, endpoint_or_url: str, json_data: dict[str, Any]) -> dict[str, Any]:
        url = _require_graph_url(
            endpoint_or_url
            if endpoint_or_url.startswith("http")
            else f"{GRAPH_BASE_URL}{endpoint_or_url}"
        )

        try:
            resp = await self._post_raw(url, self.headers, json_data=json_data)
        except httpx.HTTPStatusError as exc:
            msg = f"Graph API POST failed after retries: {exc}"
            raise GraphAPIError(msg) from exc
        except httpx.RequestError as exc:
            msg = f"Network error: {exc}"
            raise GraphAPIError(msg) from exc

        if resp.status_code == 401:
            msg = "Graph access token expired or revoked (401) — re-authenticate."
            raise TokenExpiredError(msg)
        if resp.status_code not in (200, 201, 202, 204):
            msg = f"Graph API POST error [{resp.status_code}]"
            raise GraphAPIError(msg)

        return cast("dict[str, Any]", resp.json()) if resp.status_code != 204 else {}

    async def get_all_pages(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        max_pages: int = 100,
        max_items: int = 10_000,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen_links: set[str] = set()
        next_link: str | None = (
            endpoint if endpoint.startswith("http") else f"{GRAPH_BASE_URL}{endpoint}"
        )

        pages = 0
        first = True
        while next_link:
            if next_link in seen_links:
                log.warning("Circular pagination detected, breaking loop for: %s", next_link)
                break
            seen_links.add(next_link)
            pages += 1
            if pages > max_pages:
                log.warning("Pagination page cap (%d) hit for: %s", max_pages, endpoint)
                break
            page_data = await self.get(next_link, params=params if first else None)
            first = False
            items.extend(page_data.get("value", []))
            if len(items) >= max_items:
                log.warning("Pagination item cap (%d) hit for: %s", max_items, endpoint)
                return items[:max_items]
            next_link = page_data.get("@odata.nextLink")

        return items

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "GraphClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
