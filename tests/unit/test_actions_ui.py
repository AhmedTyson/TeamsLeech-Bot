from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pyrogram import Client

from teamsleech.tg_bot.handlers.actions_ui import register_actions_ui

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_app():
    app = MagicMock(spec=Client)
    # Mock decorators
    app.on_message = MagicMock(return_value=lambda f: f)
    app.on_callback_query = MagicMock(return_value=lambda f: f)
    return app

@pytest.fixture
def mock_handlers(mock_app):
    register_actions_ui(mock_app)
    # Extract the registered handlers
    # app.on_message/callback_query were called with filters, returning decorators
    # In our mock, they returned decorators that return the functions verbatim
    # So we can patch `app.on_message` to capture the function
    return mock_app

# To test the handlers, we need to extract them from the app setup.
# Let's extract them properly.
@pytest.fixture
def handlers():
    registered = {}
    
    def on_message_mock(*args, **kwargs):
        def decorator(f):
            registered['message'] = f
            return f
        return decorator
        
    def on_cb_mock(*args, **kwargs):
        def decorator(f):
            registered['callback'] = f
            return f
        return decorator
        
    app = MagicMock(spec=Client)
    app.on_message = on_message_mock
    app.on_callback_query = on_cb_mock
    
    register_actions_ui(app)
    return registered

async def test_handle_runner_cmd(handlers):
    client = MagicMock()
    message = MagicMock()
    message.reply = AsyncMock()
    
    with patch("teamsleech.tg_bot.handlers.actions_ui.build_actions_keyboard") as mock_kb:
        mock_kb.return_value = "mock_keyboard"
        await handlers['message'](client, message)
        
        message.reply.assert_called_once()
        args, kwargs = message.reply.call_args
        assert "GitHub Actions Control Panel" in args[0]
        assert kwargs["reply_markup"] == "mock_keyboard"

async def test_handle_action_btn_run_success(handlers):
    client = MagicMock()
    cb = MagicMock()
    cb.data = "act:run"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    
    with patch("teamsleech.tg_bot.handlers.actions_ui.trigger_workflow", new_callable=AsyncMock) as mock_trigger, \
         patch("teamsleech.tg_bot.handlers.actions_ui.safe_edit_text", new_callable=AsyncMock) as mock_edit, \
         patch("teamsleech.tg_bot.handlers.actions_ui.build_actions_keyboard") as mock_kb:
        
        mock_kb.return_value = "mock_keyboard"
        await handlers['callback'](client, cb)
        
        cb.answer.assert_called_once_with("Triggering workflow...")
        mock_trigger.assert_called_once()
        mock_edit.assert_called_once()
        args, kwargs = mock_edit.call_args
        assert "Workflow triggered successfully!" in args[1]
        assert kwargs["reply_markup"] == "mock_keyboard"

async def test_handle_action_btn_status_empty(handlers):
    client = MagicMock()
    cb = MagicMock()
    cb.data = "act:status"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    
    with patch("teamsleech.tg_bot.handlers.actions_ui.get_active_runs", new_callable=AsyncMock) as mock_get, \
         patch("teamsleech.tg_bot.handlers.actions_ui.safe_edit_text", new_callable=AsyncMock) as mock_edit, \
         patch("teamsleech.tg_bot.handlers.actions_ui.build_actions_keyboard"):
        
        mock_get.return_value = []
        await handlers['callback'](client, cb)
        
        cb.answer.assert_called_once_with("Checking status...")
        mock_edit.assert_called_once()
        args, _ = mock_edit.call_args
        assert "No active runs" in args[1]

async def test_handle_action_btn_status_with_runs(handlers):
    client = MagicMock()
    cb = MagicMock()
    cb.data = "act:status"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    
    with patch("teamsleech.tg_bot.handlers.actions_ui.get_active_runs", new_callable=AsyncMock) as mock_get, \
         patch("teamsleech.tg_bot.handlers.actions_ui.safe_edit_text", new_callable=AsyncMock) as mock_edit, \
         patch("teamsleech.tg_bot.handlers.actions_ui.build_actions_keyboard"):
        
        mock_get.return_value = [
            {"name": "Run1", "id": 1, "status": "queued"},
            {"name": "Run2", "id": 2, "status": "in_progress"}
        ]
        await handlers['callback'](client, cb)
        
        mock_edit.assert_called_once()
        args, _ = mock_edit.call_args
        assert "Run1" in args[1]
        assert "Run2" in args[1]
        assert "queued" in args[1]
        assert "in_progress" in args[1]

async def test_handle_action_btn_cancel_empty(handlers):
    client = MagicMock()
    cb = MagicMock()
    cb.data = "act:cancel"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    
    with patch("teamsleech.tg_bot.handlers.actions_ui.get_active_runs", new_callable=AsyncMock) as mock_get, \
         patch("teamsleech.tg_bot.handlers.actions_ui.safe_edit_text", new_callable=AsyncMock) as mock_edit:
        
        mock_get.return_value = []
        await handlers['callback'](client, cb)
        
        cb.answer.assert_called_once_with("Fetching active runs to cancel...")
        mock_edit.assert_called_once()
        args, _ = mock_edit.call_args
        assert "No active runs to cancel" in args[1]

async def test_handle_action_btn_cancel_with_runs(handlers):
    client = MagicMock()
    cb = MagicMock()
    cb.data = "act:cancel"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    
    with patch("teamsleech.tg_bot.handlers.actions_ui.get_active_runs", new_callable=AsyncMock) as mock_get, \
         patch("teamsleech.tg_bot.handlers.actions_ui.cancel_run", new_callable=AsyncMock) as mock_cancel, \
         patch("teamsleech.tg_bot.handlers.actions_ui.safe_edit_text", new_callable=AsyncMock) as mock_edit:
        
        mock_get.return_value = [{"id": 10}, {"id": 20}]
        await handlers['callback'](client, cb)
        
        assert mock_cancel.call_count == 2
        mock_cancel.assert_any_call(10)
        mock_cancel.assert_any_call(20)
        
        # Edit text should be called twice (one for progress, one for success)
        assert mock_edit.call_count == 2
        args, _ = mock_edit.call_args
        assert "Successfully cancelled 2 run" in args[1]

async def test_handle_action_btn_exception(handlers):
    client = MagicMock()
    cb = MagicMock()
    cb.data = "act:run"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    
    with patch("teamsleech.tg_bot.handlers.actions_ui.trigger_workflow", new_callable=AsyncMock) as mock_trigger, \
         patch("teamsleech.tg_bot.handlers.actions_ui.safe_edit_text", new_callable=AsyncMock) as mock_edit:
        
        mock_trigger.side_effect = Exception("API Error")
        await handlers['callback'](client, cb)
        
        mock_edit.assert_called_once()
        args, _ = mock_edit.call_args
        assert "Error communicating with GitHub" in args[1]
        assert "API Error" in args[1]
