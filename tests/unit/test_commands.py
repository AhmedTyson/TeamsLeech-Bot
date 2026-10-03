from unittest.mock import AsyncMock, MagicMock

import pytest
from pyrogram.types import Chat

from teamsleech.models.domain import SubjectConfig
from teamsleech.tg_bot.handlers.commands import register_commands


@pytest.fixture
def mock_scanner():
    scanner = MagicMock()
    scanner.load_subjects.return_value = [
        SubjectConfig(name="Math", short="M", doctor="Dr. Smith"),
        SubjectConfig(name="Physics", short="P", doctor="Dr. Jones")
    ]
    return scanner

@pytest.fixture
def mock_state():
    state = MagicMock()
    session_mock = MagicMock()
    state.get_session.return_value = session_mock
    return state

@pytest.fixture
def mock_discovery():
    return MagicMock()

@pytest.mark.asyncio
async def test_commands_handlers(mock_scanner, mock_state, mock_discovery):
    handlers = {}
    mock_client = MagicMock()
    
    def on_message_decorator(*args, **kwargs):
        def wrapper(func):
            handlers[func.__name__] = func
            return func
        return wrapper
        
    mock_client.on_message.side_effect = on_message_decorator
    
    register_commands(mock_client, mock_scanner, mock_state, mock_discovery)
    
    assert "handle_start" in handlers
    assert "handle_check" in handlers
    assert "handle_subjects" in handlers
    
    # Test handle_start
    msg = AsyncMock()
    await handlers["handle_start"](mock_client, msg)
    msg.reply.assert_called_once()
    assert "𝗧𝗲𝗮𝗺𝘀𝗟𝗲𝗲𝗰𝗵 𝗕𝗼𝘁" in msg.reply.call_args[0][0]
    
    # Test handle_check
    msg = AsyncMock()
    await handlers["handle_check"](mock_client, msg)
    msg.reply.assert_called_once()
    assert "What do you want to check?" in msg.reply.call_args[0][0]
    
    # Test handle_subjects
    msg = AsyncMock()
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = 123
    await handlers["handle_subjects"](mock_client, msg)
    msg.reply.assert_called_once()
    assert "Subjects (2)" in msg.reply.call_args[0][0]
    assert "1. **Math**" in msg.reply.call_args[0][0]

    assert "handle_cancel_workflow" in handlers
    assert "handle_runner_removed" in handlers


@pytest.mark.asyncio
async def test_cancel_workflow_idle(mock_scanner, mock_state, mock_discovery):
    from unittest.mock import patch
    handlers = {}
    mock_client = MagicMock()
    mock_client.on_message.side_effect = (
        lambda *a, **k: (lambda f: handlers.setdefault(f.__name__, f) or f)
    )
    register_commands(mock_client, mock_scanner, mock_state, mock_discovery)
    msg = AsyncMock()
    with (
        patch(
            "teamsleech.tg_bot.handlers.commands.get_active_runs",
            AsyncMock(return_value=[]),
        ),
        patch(
            "teamsleech.tg_bot.handlers.commands.safe_edit_text",
            AsyncMock(),
        ) as mock_edit,
    ):
        await handlers["handle_cancel_workflow"](mock_client, msg)
    assert "idle" in mock_edit.await_args.args[1]


@pytest.mark.asyncio
async def test_cancel_workflow_cancels_runs(mock_scanner, mock_state, mock_discovery):
    from unittest.mock import patch
    handlers = {}
    mock_client = MagicMock()
    mock_client.on_message.side_effect = (
        lambda *a, **k: (lambda f: handlers.setdefault(f.__name__, f) or f)
    )
    register_commands(mock_client, mock_scanner, mock_state, mock_discovery)
    msg = AsyncMock()
    with (
        patch(
            "teamsleech.tg_bot.handlers.commands.get_active_runs",
            AsyncMock(return_value=[{"id": 1}, {"id": 2}]),
        ),
        patch(
            "teamsleech.tg_bot.handlers.commands.cancel_run",
            AsyncMock(),
        ) as mock_cancel,
        patch(
            "teamsleech.tg_bot.handlers.commands.safe_edit_text",
            AsyncMock(),
        ) as mock_edit,
    ):
        await handlers["handle_cancel_workflow"](mock_client, msg)
    assert mock_cancel.await_count == 2
    assert "Cancelled 2" in mock_edit.await_args.args[1]


@pytest.mark.asyncio
async def test_cancel_workflow_github_error(mock_scanner, mock_state, mock_discovery):
    from unittest.mock import patch
    handlers = {}
    mock_client = MagicMock()
    mock_client.on_message.side_effect = (
        lambda *a, **k: (lambda f: handlers.setdefault(f.__name__, f) or f)
    )
    register_commands(mock_client, mock_scanner, mock_state, mock_discovery)
    msg = AsyncMock()
    import httpx
    with (
        patch(
            "teamsleech.tg_bot.handlers.commands.get_active_runs",
            AsyncMock(side_effect=httpx.RequestError("down")),
        ),
        patch(
            "teamsleech.tg_bot.handlers.commands.safe_edit_text",
            AsyncMock(),
        ) as mock_edit,
    ):
        await handlers["handle_cancel_workflow"](mock_client, msg)
    assert "unreachable" in mock_edit.await_args.args[1]
