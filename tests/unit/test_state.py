import json
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock

import pytest

from teamsleech.models.domain import UserSession
from teamsleech.services.state import StateManager

FAKE_CHAT_ID = 67890


@pytest.fixture
def state_manager(mock_pyrogram_client):
    sm = StateManager(mock_pyrogram_client, FAKE_CHAT_ID)
    sm._initialized = True
    return sm


class TestSessionManagement:
    def test_get_session_creates_new(self, state_manager):
        session = state_manager.get_session(111)
        assert isinstance(session, UserSession)
        assert session.is_searching_teams is False

    def test_get_session_returns_same(self, state_manager):
        s1 = state_manager.get_session(222)
        s2 = state_manager.get_session(222)
        assert s1 is s2

    def test_get_session_different_users(self, state_manager):
        s1 = state_manager.get_session(1)
        s2 = state_manager.get_session(2)
        assert s1 is not s2

    def test_clear_session(self, state_manager):
        state_manager.get_session(333)
        assert 333 in state_manager._sessions
        state_manager.clear_session(333)
        assert 333 not in state_manager._sessions

    def test_clear_session_nonexistent(self, state_manager):
        state_manager.clear_session(999)


class TestLastRun:
    async def test_default_is_min_datetime(self, state_manager):
        result = state_manager.get_last_run("Unknown Subject")
        assert result == datetime.min.replace(tzinfo=UTC)

    async def test_save_and_get_last_run(self, state_manager):
        ts = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        assert state_manager._initialized
        state_manager._push_to_telegram = AsyncMock()

        await state_manager.save_last_run("Math", ts)
        result = state_manager.get_last_run("Math")
        assert result == ts

    async def test_save_last_run_default_timestamp(self, state_manager):
        state_manager._push_to_telegram = AsyncMock()
        before = datetime.now(UTC)
        await state_manager.save_last_run("Physics")
        after = datetime.now(UTC)
        result = state_manager.get_last_run("Physics")
        assert before <= result <= after

    async def test_get_last_run_from_dict_value(self, state_manager):
        state_manager._subject_cache = {
            "math": {"last_run": "2024-06-01T12:00:00+00:00", "last_lecture": 5}
        }
        result = state_manager.get_last_run("Math")
        assert result == datetime(2024, 6, 1, 12, 0, tzinfo=UTC)


class TestLastLecture:
    async def test_default_is_zero(self, state_manager):
        result = state_manager.get_last_lecture("Unknown")
        assert result == 0

    async def test_save_and_get_last_lecture(self, state_manager):
        state_manager._push_to_telegram = AsyncMock()
        await state_manager.save_last_lecture("Math", 42)
        result = state_manager.get_last_lecture("Math")
        assert result == 42

    async def test_get_last_lecture_from_dict(self, state_manager):
        state_manager._subject_cache = {
            "math": {"last_run": "2024-01-01T00:00:00+00:00", "last_lecture": 10}
        }
        result = state_manager.get_last_lecture("Math")
        assert result == 10


class TestInitialize:
    async def test_initialized_skip(self, state_manager):
        state_manager._initialized = True
        state_manager.client.get_chat = AsyncMock()
        await state_manager.initialize()
        state_manager.client.get_chat.assert_not_called()

    async def test_no_pinned_message_creates_empty(self, state_manager):
        state_manager._initialized = False
        chat = AsyncMock()
        chat.pinned_message = None
        state_manager.client.get_chat = AsyncMock(return_value=chat)
        await state_manager.initialize()
        assert state_manager._initialized
        assert state_manager._subject_cache == {}

    async def test_load_from_document(self, state_manager):
        state_manager._initialized = False
        data = json.dumps({"math": {"last_run": "2024-06-01T00:00:00+00:00"}})
        buf = BytesIO(data.encode())

        chat = AsyncMock()
        doc = AsyncMock()
        doc.document.file_name = "teamsleech_state.json"
        chat.pinned_message = doc
        state_manager.client.get_chat = AsyncMock(return_value=chat)
        state_manager._download_document = AsyncMock(return_value=buf)
        state_manager._push_to_telegram = AsyncMock()

        await state_manager.initialize()
        assert "math" in state_manager._subject_cache

    async def test_upgrade_legacy_text(self, state_manager):
        state_manager._initialized = False
        chat = AsyncMock()
        msg = AsyncMock()
        msg.id = 1
        msg.text = (
            "#TEAMSLEECH_STATE\n"
            "**⚠️ DO NOT DELETE THIS MESSAGE**\n"
            "_This acts as the database for the bot._\n\n"
            '=====JSON_START=====\n{"math": {"last_run": "2024-06-01T00:00:00+00:00"}}\n=====JSON_END====='
        )
        chat.pinned_message = msg
        state_manager.client.get_chat = AsyncMock(return_value=chat)
        state_manager._push_to_telegram = AsyncMock()

        await state_manager.initialize()
        assert "math" in state_manager._subject_cache
        state_manager._push_to_telegram.assert_awaited_once()


class TestPushToTelegram:
    async def test_push_sends_document_and_pins(self, state_manager):
        state_manager._msg_id = None
        sent_msg = AsyncMock()
        sent_msg.id = 99
        state_manager._send_state_doc = AsyncMock(return_value=sent_msg)
        state_manager.client.pin = AsyncMock()
        state_manager._subject_cache = {"test": {"last_run": "2024-01-01T00:00:00+00:00"}}

        await state_manager._push_to_telegram()
        assert state_manager._msg_id == 99
        sent_msg.pin.assert_awaited_once()

    async def test_push_replaces_old_message(self, state_manager):
        state_manager._msg_id = 5
        sent_msg = AsyncMock()
        sent_msg.id = 100
        state_manager._send_state_doc = AsyncMock(return_value=sent_msg)
        state_manager.client.delete_messages = AsyncMock()

        await state_manager._push_to_telegram()
        state_manager.client.delete_messages.assert_awaited_once_with(
            FAKE_CHAT_ID, 5
        )
