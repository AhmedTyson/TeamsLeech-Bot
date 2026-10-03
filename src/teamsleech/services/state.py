"""In-memory per-chat sessions. No persistence: every scan covers everything,
so there is nothing to remember between runs."""

from teamsleech.models.domain import UserSession


class StateManager:
    def __init__(self, client, chat_id: int):
        self.client = client
        self.chat_id = chat_id
        self._sessions: dict[int, UserSession] = {}

    def get_session(self, user_id: int) -> UserSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession()
        return self._sessions[user_id]

    def clear_session(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)
