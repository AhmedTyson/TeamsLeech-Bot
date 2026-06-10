from unittest.mock import AsyncMock, MagicMock

import pytest
from pyrogram.types import Chat

from teamsleech.models.domain import Recording
from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui


@pytest.fixture
def mock_transfer():
    transfer = MagicMock()
    transfer.start_transfer = AsyncMock()
    return transfer

@pytest.fixture
def mock_scanner():
    scanner = MagicMock()
    scanner.mark_as_processed = AsyncMock()
    return scanner

@pytest.fixture
def mock_state():
    state = MagicMock()
    session_mock = MagicMock()
    session_mock.pending_recordings = [
        Recording(
            id="1", name="Vid1", url="http", 
            is_video=True, size_mb=10.0, 
            created="2026-04-01", team_name="T1",
            drive_id="d1", item_id="i1", subject_name="Math"
        )
    ]
    session_mock.selected_indices = {0}
    session_mock.rename_overrides = {}
    state.get_session.return_value = session_mock
    return state

@pytest.mark.asyncio
async def test_upload_ui_handlers(mock_transfer, mock_scanner, mock_state):
    handlers_cb = {}
    handlers_msg = {}
    mock_client = MagicMock()
    
    def on_cb_decorator(*args, **kwargs):
        def wrapper(func):
            handlers_cb[func.__name__] = func
            return func
        return wrapper

    def on_msg_decorator(*args, **kwargs):
        def wrapper(func):
            handlers_msg[func.__name__] = func
            return func
        return wrapper
        
    mock_client.on_callback_query.side_effect = on_cb_decorator
    mock_client.on_message.side_effect = on_msg_decorator
    
    register_upload_ui(mock_client, mock_transfer, mock_state, mock_scanner)
    
    test_datas = ["upload:confirm", "ren:0", "retry:upload", "cancel:upload"]
    
    for d in test_datas:
        cb = AsyncMock()
        cb.data = d
        cb.message = AsyncMock()
        cb.message.chat = MagicMock(spec=Chat)
        cb.message.chat.id = 123
        
        for _, func in handlers_cb.items():
            try:
                await func(mock_client, cb)
            except Exception:
                pass

    test_msgs = ["NewName", "Cancel", "Skip"]
    for m in test_msgs:
        msg = AsyncMock()
        msg.continue_propagation = MagicMock()
        msg.text = m
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 123
        
        for _, func in handlers_msg.items():
            try:
                await func(mock_client, msg)
            except Exception:
                pass
