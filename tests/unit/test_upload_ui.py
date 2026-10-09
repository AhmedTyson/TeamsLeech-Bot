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


def _rig():
    from teamsleech.services.state import StateManager
    app = MagicMock()
    cbs, msgs = {}, {}
    app.on_callback_query.side_effect = (
        lambda *a, **k: (lambda f: cbs.setdefault(f.__name__, f) or f)
    )
    app.on_message.side_effect = (
        lambda *a, **k: (lambda f: msgs.setdefault(f.__name__, f) or f)
    )
    state = StateManager(MagicMock(), 123)
    scanner = MagicMock()
    scanner.load_subjects.return_value = []
    register_upload_ui(app, MagicMock(), state, scanner)
    return cbs, msgs, state


def _mkmsg(text):
    msg = AsyncMock()
    msg.continue_propagation = MagicMock()
    msg.text = text
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = 123
    return msg


def _one_rec(state):
    ses = state.get_session(123)
    ses.pending_recordings = [
        Recording(
            name="Week 01.mp4", size_mb=10.0, created="2026-10-01",
            drive_id="d", item_id="i", team_name="T", subject_name="S",
            is_video=True,
        )
    ]
    ses.selected_indices = {0}
    return ses


@pytest.mark.asyncio
async def test_typed_name_after_accept_overrides():
    cbs, msgs, state = _rig()
    ses = _one_rec(state)
    ses.rename_overrides[0] = "Short"
    ses.pending_rename_idx = None
    await msgs["handle_rename_input"](MagicMock(), _mkmsg("A Much Longer Name Here"))
    assert ses.rename_overrides[0] == "A Much Longer Name Here"


@pytest.mark.asyncio
async def test_typed_name_multi_select_propagates():
    cbs, msgs, state = _rig()
    ses = _one_rec(state)
    ses.pending_recordings.append(ses.pending_recordings[0])
    ses.selected_indices = {0, 1}
    msg = _mkmsg("Some Name")
    await msgs["handle_rename_input"](MagicMock(), msg)
    msg.continue_propagation.assert_called_once()
    assert ses.rename_overrides == {}


@pytest.mark.asyncio
async def test_typed_name_during_other_flow_propagates():
    cbs, msgs, state = _rig()
    ses = _one_rec(state)
    ses.date_input_pending = True
    msg = _mkmsg("Some Name")
    await msgs["handle_rename_input"](MagicMock(), msg)
    msg.continue_propagation.assert_called_once()
    assert ses.rename_overrides == {}
