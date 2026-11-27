"""Handler-level tests for the forward-a-file DM fallback."""

import datetime

from teamsleech.models.domain import SubjectConfig
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.handlers import file_drop as fd


class FakeApp:
    def __init__(self):
        self.msg_handlers = []

    def on_message(self, _filters):
        def deco(fn):
            self.msg_handlers.append(fn)
            return fn
        return deco


class FakeMedia:
    def __init__(self, file_name=None):
        self.file_name = file_name


class FakeMessage:
    def __init__(self, chat_id=123, msg_id=10, video=None, audio=None,
                 document=None, date=None):
        self.chat = type("Chat", (), {"id": chat_id})()
        self.id = msg_id
        self.video = video
        self.audio = audio
        self.document = document
        self.date = date or datetime.datetime(2026, 11, 28, 10, 0, 0)
        self.replies = []

    async def reply(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return self


class FakeScanner:
    def __init__(self, subjects):
        self._subjects = subjects

    def load_subjects(self):
        return self._subjects


def _subject(name="Math", short="MTH"):
    return SubjectConfig(
        name=name, short=short, doctor="Smith", kind="lecture",
        keywords=[name.lower()], topic_id=5, next_no=3,
    )


def test_describe_media():
    v = FakeMessage(video=FakeMedia("lec.mp4"))
    assert fd.describe_media(v) == ("lec.mp4", "video")
    a = FakeMessage(audio=FakeMedia(None))
    assert fd.describe_media(a) == ("audio.m4a", "audio")
    d = FakeMessage(document=FakeMedia("slides.pdf"))
    assert fd.describe_media(d) == ("slides.pdf", "document")
    assert fd.describe_media(FakeMessage()) is None


async def test_dropped_video_registers_and_asks_subject():
    app, state = FakeApp(), StateManager(client=None, chat_id=123)
    fd.register_file_drop(app, state, FakeScanner([_subject()]))
    handler = app.msg_handlers[0]

    msg = FakeMessage(video=FakeMedia("Lecture 4.mp4"))
    await handler(None, msg)

    uploads = state.get_session(123).last_uploads
    assert len(uploads) == 1
    item = uploads[0]
    assert item.name == "Lecture 4.mp4"
    assert item.message_id == msg.id
    assert item.chat_id == 123
    assert item.subject_name == ""
    assert item.is_video is True
    assert item.created.startswith("2026-11-28")

    assert len(msg.replies) == 1
    text, kwargs = msg.replies[0]
    assert "Lecture 4.mp4" in text
    assert "reply_markup" in kwargs  # subject keyboard shown


async def test_dropped_document_without_subjects():
    app, state = FakeApp(), StateManager(client=None, chat_id=123)
    fd.register_file_drop(app, state, FakeScanner([]))
    handler = app.msg_handlers[0]

    msg = FakeMessage(document=FakeMedia("notes.pdf"))
    await handler(None, msg)

    uploads = state.get_session(123).last_uploads
    assert len(uploads) == 1
    assert uploads[0].is_video is False
    assert "No subjects configured" in msg.replies[0][0]


async def test_same_message_never_registered_twice():
    app, state = FakeApp(), StateManager(client=None, chat_id=123)
    fd.register_file_drop(app, state, FakeScanner([_subject()]))
    handler = app.msg_handlers[0]

    msg = FakeMessage(video=FakeMedia("dup.mp4"))
    await handler(None, msg)
    await handler(None, msg)

    assert len(state.get_session(123).last_uploads) == 1
    assert len(msg.replies) == 1


async def test_default_names_when_file_name_missing():
    app, state = FakeApp(), StateManager(client=None, chat_id=123)
    fd.register_file_drop(app, state, FakeScanner([_subject()]))
    handler = app.msg_handlers[0]

    await handler(None, FakeMessage(msg_id=20, video=FakeMedia(None)))
    await handler(None, FakeMessage(msg_id=21, audio=FakeMedia(None)))

    names = [u.name for u in state.get_session(123).last_uploads]
    assert names == ["video.mp4", "audio.m4a"]
