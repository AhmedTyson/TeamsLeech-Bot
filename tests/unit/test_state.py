from teamsleech.models.domain import UserSession
from teamsleech.services.state import StateManager

FAKE_CHAT_ID = 67890


class TestSessionManagement:
    def test_get_session_creates_new(self, mock_pyrogram_client):
        sm = StateManager(mock_pyrogram_client, FAKE_CHAT_ID)
        session = sm.get_session(111)
        assert isinstance(session, UserSession)
        assert session.is_searching_teams is False

    def test_get_session_returns_same(self, mock_pyrogram_client):
        sm = StateManager(mock_pyrogram_client, FAKE_CHAT_ID)
        assert sm.get_session(222) is sm.get_session(222)

    def test_get_session_different_users(self, mock_pyrogram_client):
        sm = StateManager(mock_pyrogram_client, FAKE_CHAT_ID)
        assert sm.get_session(1) is not sm.get_session(2)

    def test_clear_session(self, mock_pyrogram_client):
        sm = StateManager(mock_pyrogram_client, FAKE_CHAT_ID)
        sm.get_session(333)
        assert 333 in sm._sessions
        sm.clear_session(333)
        assert 333 not in sm._sessions

    def test_clear_session_nonexistent(self, mock_pyrogram_client):
        sm = StateManager(mock_pyrogram_client, FAKE_CHAT_ID)
        sm.clear_session(999)

    def test_no_persistence_surface(self, mock_pyrogram_client):
        sm = StateManager(mock_pyrogram_client, FAKE_CHAT_ID)
        for attr in (
            "initialize", "get_last_run", "save_last_run",
            "get_last_lecture", "save_last_lecture",
        ):
            assert not hasattr(sm, attr), attr
