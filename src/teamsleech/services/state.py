"""In-memory per-chat sessions. No persistence: every scan covers everything,
so there is nothing to remember between runs."""

from teamsleech.models.domain import Recording, UserSession


class StateManager:
    def __init__(self, client, chat_id: int):
        self.client = client
        self.chat_id = chat_id
        self._sessions: dict[int, UserSession] = {}
        # Failed downloads live outside UserSession: they must survive a
        # rescan/clear so the user can retry them after a fresh login.
        self._failed_downloads: dict[int, list[Recording]] = {}

    def get_session(self, user_id: int) -> UserSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession()
        return self._sessions[user_id]

    def clear_session(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)

    @staticmethod
    def _rec_key(rec: Recording) -> tuple[str, str]:
        return (rec.drive_id, rec.item_id)

    def add_failed_download(self, chat_id: int, rec: Recording) -> None:
        lst = self._failed_downloads.setdefault(chat_id, [])
        if any(self._rec_key(f) == self._rec_key(rec) for f in lst):
            return
        lst.append(rec)

    def get_failed_downloads(self, chat_id: int) -> list[Recording]:
        return list(self._failed_downloads.get(chat_id, []))

    def set_failed_downloads(
        self, chat_id: int, recs: list[Recording]
    ) -> None:
        self._failed_downloads[chat_id] = list(recs)
