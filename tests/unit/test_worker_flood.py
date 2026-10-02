import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from worker.telegram import _start_client


class _FlakyClient:
    def __init__(self, failures):
        self.failures = failures
        self.starts = 0
        self.stopped = False

    async def start(self):
        from pyrogram.errors import FloodWait

        self.starts += 1
        if self.starts <= self.failures:
            raise FloodWait(3)
        return None

    async def stop(self):
        self.stopped = True


def test_start_client_succeeds_first_try():
    client = _FlakyClient(0)
    asyncio.run(_start_client(client))
    assert client.starts == 1


def test_start_client_backs_off_once_then_succeeds():
    client = _FlakyClient(1)
    with patch("asyncio.sleep", new=AsyncMock()) as nap:
        asyncio.run(_start_client(client))
    assert client.starts == 2
    nap.assert_awaited_once_with(3)


def test_start_client_gives_up_loudly():
    client = _FlakyClient(5)
    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(RuntimeError, match="TELEGRAM_SESSION_STRING"):
            asyncio.run(_start_client(client))
    assert client.starts == 2
