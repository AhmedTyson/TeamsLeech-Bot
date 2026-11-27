"""The first /link in the group doubles as publishing setup."""

import pytest

from teamsleech.core.config import settings
from teamsleech.tg_bot.handlers.commands import persist_target_chat_id


@pytest.mark.asyncio
async def test_persist_target_chat_id_saves_secret_and_memory(monkeypatch):
    saved = {}

    async def fake_rotate(name, value):
        saved[name] = value

    monkeypatch.setattr(
        "teamsleech.services.github_secrets.rotate_github_secret", fake_rotate
    )
    monkeypatch.setattr(settings, "telegram_target_chat_id", "")

    await persist_target_chat_id(-1009876543210)

    assert saved == {"TELEGRAM_TARGET_CHAT_ID": "-1009876543210"}
    assert settings.target_chat_id() == -1009876543210


@pytest.mark.asyncio
async def test_persist_target_chat_id_failure_leaves_memory_unset(monkeypatch):
    async def boom(name, value):
        raise RuntimeError("no GH_PAT")

    monkeypatch.setattr(
        "teamsleech.services.github_secrets.rotate_github_secret", boom
    )
    monkeypatch.setattr(settings, "telegram_target_chat_id", "")

    with pytest.raises(RuntimeError):
        await persist_target_chat_id(-1001)
    assert settings.target_chat_id() is None
