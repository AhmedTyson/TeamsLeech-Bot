"""Handler-level tests for the shared-link download flow (fake Telegram)."""

import pytest

from teamsleech.core.config import settings
from teamsleech.models.domain import Recording, SubjectConfig
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.handlers import link_download as ld


class FakeApp:
    def __init__(self):
        self.msg_handlers = []
        self.cb_handlers = []

    def on_message(self, _filters):
        def deco(fn):
            self.msg_handlers.append(fn)
            return fn
        return deco

    def on_callback_query(self, _filters):
        def deco(fn):
            self.cb_handlers.append(fn)
            return fn
        return deco


class FakeMessage:
    def __init__(self, text="", chat_id=None):
        self.text = text
        self.chat = type("Chat", (), {"id": chat_id or settings.telegram_chat_id})()
        self.edits = []
        self.replies = []

    async def reply(self, text, **kwargs):
        m = FakeMessage(chat_id=self.chat.id)
        m.replies.append(text)
        m.kwargs = kwargs
        self.replies.append(m)
        return m

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeCallback:
    def __init__(self, data, chat_id=None):
        self.data = data
        self.message = FakeMessage(chat_id=chat_id)
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append(text)


class FakeTransfer:
    def __init__(self, results):
        self.graph = object()
        self._results = results
        self.calls = []

    async def upload_recordings(self, recs, progress_cb=None):
        self.calls.append([r.name for r in recs])
        return self._results


class FakeScanner:
    def __init__(self, subjects):
        self._subjects = subjects

    def load_subjects(self):
        return self._subjects


def _rec():
    return Recording(
        name="Lecture 12.mp4", size_mb=250.0, created="2026-11-20",
        time="10:30", duration_ms=3_600_000, drive_id="d", item_id="i",
        team_name="🔗 shared link", subject_name="", is_video=True,
    )


def _subject():
    return SubjectConfig(
        name="FT course", short="FT", doctor="Azza Hegazy",
        keywords=["x"], kind="lecture", next_no=8,
    )


def _register(transfer, state, scanner):
    app = FakeApp()
    ld.register_link_download(app, transfer, state, scanner)
    assert len(app.msg_handlers) == 1
    assert len(app.cb_handlers) == 1
    return app.msg_handlers[0], app.cb_handlers[0]


@pytest.mark.asyncio
async def test_link_happy_path_assigns_subject(monkeypatch):
    async def fake_resolve(graph, url):
        return _rec()
    monkeypatch.setattr(ld, "resolve_share_recording", fake_resolve)

    state = StateManager(None, settings.telegram_chat_id)
    transfer = FakeTransfer([{"success": True, "message_id": 10, "chat_id": 5}])
    msg_handler, cb_handler = _register(transfer, state, FakeScanner([_subject()]))

    message = FakeMessage("https://uni.sharepoint.com/:v:/s/team/abc")
    await msg_handler(None, message)

    assert transfer.calls == [["Lecture 12.mp4"]]
    session = state.get_session(settings.telegram_chat_id)
    assert len(session.last_uploads) == 1
    assert session.last_uploads[0].subject_name == ""
    status = message.replies[0]
    assert "Pick its subject" in status.edits[-1][0]
    assert "reply_markup" in status.edits[-1][1]

    cb = FakeCallback("linksubj:FT")
    await cb_handler(None, cb)
    item = session.last_uploads[0]
    assert item.subject_name == "FT"
    assert item.assigned_no == 8
    assert item.name == "FT - L08 - Dr. Azza Hegazy.mp4"
    assert "Ready to publish" in cb.message.edits[-1][0]
    assert cb.answered == [None]


@pytest.mark.asyncio
async def test_skip_leaves_item_unassigned(monkeypatch):
    async def fake_resolve(graph, url):
        return _rec()
    monkeypatch.setattr(ld, "resolve_share_recording", fake_resolve)

    state = StateManager(None, settings.telegram_chat_id)
    transfer = FakeTransfer([{"success": True, "message_id": 10, "chat_id": 5}])
    msg_handler, cb_handler = _register(transfer, state, FakeScanner([_subject()]))

    await msg_handler(None, FakeMessage("https://uni.sharepoint.com/x"))
    cb = FakeCallback("linksubj:__skip__")
    await cb_handler(None, cb)
    item = state.get_session(settings.telegram_chat_id).last_uploads[0]
    assert item.subject_name == ""
    assert "won't publish" in cb.message.edits[-1][0]


@pytest.mark.asyncio
async def test_unresolvable_link_reports_error(monkeypatch):
    async def boom(graph, url):
        raise ValueError("Link did not resolve to a file.")
    monkeypatch.setattr(ld, "resolve_share_recording", boom)

    state = StateManager(None, settings.telegram_chat_id)
    transfer = FakeTransfer([])
    msg_handler, _ = _register(transfer, state, FakeScanner([]))

    message = FakeMessage("https://uni.sharepoint.com/bad")
    await msg_handler(None, message)
    assert transfer.calls == []
    status = message.replies[0]
    assert "Could not read that link" in status.edits[-1][0]


@pytest.mark.asyncio
async def test_download_failure_reports(monkeypatch):
    async def fake_resolve(graph, url):
        return _rec()
    monkeypatch.setattr(ld, "resolve_share_recording", fake_resolve)

    state = StateManager(None, settings.telegram_chat_id)
    transfer = FakeTransfer([{"success": False, "error": "boom"}])
    msg_handler, _ = _register(transfer, state, FakeScanner([]))

    message = FakeMessage("https://uni.sharepoint.com/x")
    await msg_handler(None, message)
    status = message.replies[0]
    assert "Download failed: boom" in status.edits[-1][0]
    assert not state.get_session(settings.telegram_chat_id).last_uploads


@pytest.mark.asyncio
async def test_plain_text_ignored(monkeypatch):
    state = StateManager(None, settings.telegram_chat_id)
    transfer = FakeTransfer([])
    msg_handler, _ = _register(transfer, state, FakeScanner([]))

    message = FakeMessage("just chatting, no links")
    await msg_handler(None, message)
    assert message.replies == []
    assert transfer.calls == []


@pytest.mark.asyncio
async def test_callback_without_pending_item(monkeypatch):
    state = StateManager(None, settings.telegram_chat_id)
    transfer = FakeTransfer([])
    _, cb_handler = _register(transfer, state, FakeScanner([_subject()]))

    cb = FakeCallback("linksubj:FT")
    await cb_handler(None, cb)
    assert cb.answered == ["Nothing waiting for a subject."]


@pytest.mark.asyncio
async def test_resolve_share_recording_via_fake_graph():
    from teamsleech.services.shares import resolve_share_recording

    class FakeGraph:
        def __init__(self, item):
            self.item = item
            self.urls = []

        async def get(self, url):
            self.urls.append(url)
            return self.item

    good = FakeGraph({
        "id": "i1", "name": "Lec.mp4", "size": 1024 * 1024,
        "createdDateTime": "2026-11-20T10:30:00Z",
        "video": {"duration": 1000},
        "parentReference": {"driveId": "d1"},
    })
    rec = await resolve_share_recording(good, "https://x.sharepoint.com/v")
    assert rec.drive_id == "d1" and rec.item_id == "i1"
    assert good.urls[0].startswith("/shares/u!")

    bad = FakeGraph({"id": "", "name": "x", "parentReference": {}})
    with pytest.raises(ValueError):
        await resolve_share_recording(bad, "https://x.sharepoint.com/v")


@pytest.mark.asyncio
async def test_no_subjects_configured(monkeypatch):
    async def fake_resolve(graph, url):
        return _rec()
    monkeypatch.setattr(ld, "resolve_share_recording", fake_resolve)

    state = StateManager(None, settings.telegram_chat_id)
    transfer = FakeTransfer([{"success": True, "message_id": 10, "chat_id": 5}])
    msg_handler, _ = _register(transfer, state, FakeScanner([]))

    message = FakeMessage("https://uni.sharepoint.com/x")
    await msg_handler(None, message)
    status = message.replies[0]
    assert "No subjects configured yet" in status.edits[-1][0]
