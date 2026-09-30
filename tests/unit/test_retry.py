from unittest.mock import AsyncMock, patch

import httpx

from teamsleech.core.retry import _is_retryable_http, honor_retry_after


def _status_error(code):
    req = httpx.Request("GET", "https://graph.microsoft.com/v1.0/me")
    return httpx.HTTPStatusError("err", request=req, response=httpx.Response(code, request=req))


class TestIsRetryable:
    def test_network_errors(self):
        assert _is_retryable_http(httpx.RequestError("x")) is True
        assert _is_retryable_http(TimeoutError()) is True
        assert _is_retryable_http(ConnectionError()) is True

    def test_throttle_and_server(self):
        assert _is_retryable_http(_status_error(429)) is True
        assert _is_retryable_http(_status_error(500)) is True
        assert _is_retryable_http(_status_error(503)) is True

    def test_client_errors_not_retried(self):
        assert _is_retryable_http(_status_error(400)) is False
        assert _is_retryable_http(_status_error(401)) is False
        assert _is_retryable_http(_status_error(404)) is False
        assert _is_retryable_http(ValueError("x")) is False


class TestHonorRetryAfter:
    async def test_no_header_no_sleep(self):
        req = httpx.Request("GET", "https://x")
        resp = httpx.Response(200, request=req)
        with patch("teamsleech.core.retry.asyncio.sleep", new=AsyncMock()) as nap:
            await honor_retry_after(resp)
        nap.assert_not_called()

    async def test_invalid_header_no_sleep(self):
        req = httpx.Request("GET", "https://x")
        resp = httpx.Response(429, headers={"retry-after": "soon"}, request=req)
        with patch("teamsleech.core.retry.asyncio.sleep", new=AsyncMock()) as nap:
            await honor_retry_after(resp)
        nap.assert_not_called()

    async def test_valid_header_capped(self):
        req = httpx.Request("GET", "https://x")
        resp = httpx.Response(429, headers={"retry-after": "9999"}, request=req)
        with patch("teamsleech.core.retry.asyncio.sleep", new=AsyncMock()) as nap:
            await honor_retry_after(resp)
        nap.assert_awaited_once_with(60.0)
