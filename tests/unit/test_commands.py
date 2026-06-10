import pytest
from unittest.mock import AsyncMock, MagicMock
from pyrogram.types import Message, Chat

from teamsleech.tg_bot.handlers.commands import register_commands
from teamsleech.models.domain import SubjectConfig

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
    assert "𝗖𝗼𝘂𝗿𝘀𝗲 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁 𝗗𝗮𝘀𝗵𝗯𝗼𝗮𝗿𝗱" in msg.reply.call_args[0][0]
    assert mock_state.get_session(123).is_searching_teams is True
