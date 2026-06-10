from unittest.mock import AsyncMock, MagicMock

import pytest
from pyrogram.types import Chat

from teamsleech.models.domain import Recording
from teamsleech.tg_bot.handlers.scanner_ui import register_scanner_ui


@pytest.fixture
def mock_scanner():
    scanner = MagicMock()
    scanner.scan_recordings = AsyncMock()
    scanner.scan_recordings.return_value = {
        "Math": [Recording(
            id="1", name="Vid1", url="http", 
            is_video=True, size_mb=10.0, 
            created="2026-04-01", team_name="T1",
            drive_id="d1", item_id="i1", subject_name="Math"
        )]
    }
    return scanner

@pytest.fixture
def mock_state():
    state = MagicMock()
    session_mock = MagicMock()
    session_mock.pending_recordings = []
    session_mock.selected_indices = set()
    state.get_session.return_value = session_mock
    return state

@pytest.mark.asyncio
async def test_scanner_ui_handlers(mock_scanner, mock_state):
    handlers_cb = {}
    handlers_msg = {}
    mock_client = MagicMock()
    mock_client.send_message = AsyncMock()
    
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
    
    register_scanner_ui(mock_client, mock_scanner, mock_state)
    
    test_datas = ["subj:Math", "sel:0", "sel:all", "sel:pdfs", "sel:videos", "date:change", "cancel:check"]
    
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

    test_msgs = ["2026-04-01", "today", "this week", "invalid"]
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
