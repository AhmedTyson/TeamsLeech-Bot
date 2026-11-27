from unittest.mock import AsyncMock, MagicMock

import pytest

from teamsleech.models.domain import Recording
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.retry_failed import record_failed, retry_failed_downloads


def make_rec(item_id="i1", drive_id="d1", name="Lec1.mp4"):
    return Recording(
        name=name,
        size_mb=10.0,
        created="2026-11-01",
        drive_id=drive_id,
        item_id=item_id,
        team_name="T",
        subject_name="S",
        is_video=True,
    )


@pytest.fixture
def state():
    return StateManager(MagicMock(), 123)


def test_record_failed_dedupes(state):
    rec = make_rec()
    record_failed(state, 123, rec)
    record_failed(state, 123, rec)
    assert len(state.get_failed_downloads(123)) == 1
    record_failed(state, 123, make_rec(item_id="i2"))
    assert len(state.get_failed_downloads(123)) == 2


@pytest.mark.asyncio
async def test_retry_empty(state):
    msg = AsyncMock()
    msg.chat.id = 123
    n = await retry_failed_downloads(MagicMock(), msg, MagicMock(), state)
    assert n == 0
    msg.reply.assert_called_once()
    assert "Nothing waiting" in msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_retry_success_clears(state):
    rec = make_rec()
    record_failed(state, 123, rec)
    transfer = MagicMock()

    async def fake_upload(recs, cb):
        await cb("file_done", {"index": 0, "name": rec.name})
        return [{"success": True, "rec": rec, "message_id": 1, "chat_id": 123}]

    transfer.upload_recordings = AsyncMock(side_effect=fake_upload)
    msg = AsyncMock()
    msg.chat.id = 123
    n = await retry_failed_downloads(MagicMock(), msg, transfer, state)
    assert n == 1
    assert state.get_failed_downloads(123) == []
    texts = [c.args[0] for c in msg.reply.call_args_list]
    assert any("Retrying 1" in t for t in texts)
    assert any("Retry complete" in t for t in texts)


@pytest.mark.asyncio
async def test_retry_failure_keeps_and_reports(state):
    rec = make_rec()
    record_failed(state, 123, rec)
    transfer = MagicMock()

    async def fake_upload(recs, cb):
        await cb(
            "error", {"index": 0, "name": rec.name, "error": "401 denied Login"}
        )
        return [{"success": False, "rec": rec}]

    transfer.upload_recordings = AsyncMock(side_effect=fake_upload)
    msg = AsyncMock()
    msg.chat.id = 123
    n = await retry_failed_downloads(MagicMock(), msg, transfer, state)
    assert n == 0
    assert len(state.get_failed_downloads(123)) == 1
    texts = [c.args[0] for c in msg.reply.call_args_list]
    assert any("failed again" in t for t in texts)
    assert any("Still failing" in t for t in texts)
    # The per-file failure message carries the login/retry keyboard.
    kb = msg.reply.call_args_list[1].kwargs.get("reply_markup")
    assert kb is not None


@pytest.mark.asyncio
async def test_retry_partial_success(state):
    rec1, rec2 = make_rec(item_id="i1"), make_rec(item_id="i2", name="Lec2.mp4")
    record_failed(state, 123, rec1)
    record_failed(state, 123, rec2)
    transfer = MagicMock()

    async def fake_upload(recs, cb):
        await cb("file_done", {"index": 0, "name": rec1.name})
        await cb("error", {"index": 1, "name": rec2.name, "error": "timeout"})
        return [
            {"success": True, "rec": rec1},
            {"success": False, "rec": rec2},
        ]

    transfer.upload_recordings = AsyncMock(side_effect=fake_upload)
    msg = AsyncMock()
    msg.chat.id = 123
    n = await retry_failed_downloads(MagicMock(), msg, transfer, state)
    assert n == 1
    remaining = state.get_failed_downloads(123)
    assert len(remaining) == 1
    assert remaining[0].item_id == "i2"
    texts = [c.args[0] for c in msg.reply.call_args_list]
    assert any("1 uploaded" in t and "1 still failing" in t for t in texts)


@pytest.mark.asyncio
async def test_retry_run_exception(state):
    rec = make_rec()
    record_failed(state, 123, rec)
    transfer = MagicMock()
    transfer.upload_recordings = AsyncMock(side_effect=RuntimeError("boom"))
    msg = AsyncMock()
    msg.chat.id = 123
    n = await retry_failed_downloads(MagicMock(), msg, transfer, state)
    assert n == 0
    assert len(state.get_failed_downloads(123)) == 1
    texts = [c.args[0] for c in msg.reply.call_args_list]
    assert any("Retry run failed" in t for t in texts)


def test_failure_keyboard_has_retry_and_login():
    from teamsleech.tg_bot.handlers.upload_ui import _failure_keyboard

    kb = _failure_keyboard("SharePoint download failed [401]")
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "retry:failed" in callbacks
    assert "login:start" in callbacks


@pytest.mark.asyncio
async def test_login_success_triggers_auto_retry(monkeypatch):
    from teamsleech.tg_bot.handlers.commands import register_commands

    handlers = {}
    mock_client = MagicMock()

    def on_message_decorator(*args, **kwargs):
        def wrapper(func):
            handlers[func.__name__] = func
            return func

        return wrapper

    mock_client.on_message.side_effect = on_message_decorator

    rec = make_rec()
    state = MagicMock()
    state.get_failed_downloads.return_value = [rec]
    transfer = MagicMock()

    register_commands(
        mock_client, MagicMock(), state, MagicMock(), transfer
    )

    monkeypatch.setattr(
        "teamsleech.services.reauth.run_reauth_flow",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "teamsleech.services.auth.authenticate",
        AsyncMock(return_value="token"),
    )
    retry_mock = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "teamsleech.tg_bot.retry_failed.retry_failed_downloads", retry_mock
    )

    msg = AsyncMock()
    await handlers["handle_login"](mock_client, msg)
    retry_mock.assert_called_once()
    texts = [c.args[0] for c in msg.reply.call_args_list]
    assert any("Retrying 1 failed" in t for t in texts)


@pytest.mark.asyncio
async def test_login_success_no_failures_no_retry(monkeypatch):
    from teamsleech.tg_bot.handlers.commands import register_commands

    handlers = {}
    mock_client = MagicMock()

    def on_message_decorator(*args, **kwargs):
        def wrapper(func):
            handlers[func.__name__] = func
            return func

        return wrapper

    mock_client.on_message.side_effect = on_message_decorator

    state = MagicMock()
    state.get_failed_downloads.return_value = []

    register_commands(
        mock_client, MagicMock(), state, MagicMock(), MagicMock()
    )

    monkeypatch.setattr(
        "teamsleech.services.reauth.run_reauth_flow",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "teamsleech.services.auth.authenticate",
        AsyncMock(return_value="token"),
    )
    retry_mock = AsyncMock()
    monkeypatch.setattr(
        "teamsleech.tg_bot.retry_failed.retry_failed_downloads", retry_mock
    )

    msg = AsyncMock()
    await handlers["handle_login"](mock_client, msg)
    retry_mock.assert_not_called()
