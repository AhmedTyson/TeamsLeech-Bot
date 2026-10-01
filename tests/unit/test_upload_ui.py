from unittest.mock import AsyncMock, MagicMock

import pytest

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
            id="1",
            name="Vid1",
            url="http",
            is_video=True,
            size_mb=10.0,
            created="2026-04-01",
            team_name="T1",
            drive_id="d1",
            item_id="i1",
            subject_name="Math",
        )
    ]
    session_mock.selected_indices = {0}
    session_mock.rename_overrides = {}
    state.get_session.return_value = session_mock
    return state


async def test_rename_btn_rejects_malformed_data(mock_transfer, mock_scanner, mock_state):
    handlers_cb = {}
    mock_client = MagicMock()
    mock_client.on_callback_query.side_effect = lambda *a, **k: (
        lambda f: handlers_cb.setdefault(f.__name__, f)
    )
    mock_client.on_message.side_effect = lambda *a, **k: lambda f: f
    register_upload_ui(mock_client, mock_transfer, mock_state, mock_scanner)

    cb = AsyncMock()
    cb.data = "ren:abc"
    cb.message = AsyncMock()
    cb.message.chat.id = 123
    await handlers_cb["handle_rename_btn"](mock_client, cb)
    cb.answer.assert_awaited_once_with("Invalid recording!", show_alert=True)


async def test_upload_confirm_batches_state_without_mutating(
    mock_scanner,
):
    from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui

    rec = Recording(
        name="Vid1",
        is_video=True,
        size_mb=10.0,
        created="2026-04-01",
        time="10:00",
        duration_ms=0,
        team_name="T1",
        drive_id="d1",
        item_id="i1",
        subject_name="Math",
    )
    session = MagicMock()
    session.pending_recordings = [rec]
    session.selected_indices = {0}
    session.rename_overrides = {0: "Renamed"}
    state = MagicMock()
    state.get_session.return_value = session
    state.save_subject_state = AsyncMock()
    transfer = MagicMock()
    transfer.upload_recordings = AsyncMock(
        return_value=[{"success": True, "error": None, "rec": rec}]
    )

    handlers_cb = {}
    mock_client = MagicMock()
    mock_client.on_callback_query.side_effect = lambda *a, **k: (
        lambda f: handlers_cb.setdefault(f.__name__, f)
    )
    mock_client.on_message.side_effect = lambda *a, **k: lambda f: f
    register_upload_ui(mock_client, transfer, state, mock_scanner)

    cb = AsyncMock()
    cb.data = "upload:confirm"
    cb.message = AsyncMock()
    cb.message.chat.id = 123
    cb.message.reply = AsyncMock(return_value=AsyncMock(text="progress"))
    await handlers_cb["handle_upload"](mock_client, cb)

    assert rec.name == "Vid1"
    sent = transfer.upload_recordings.await_args.args[0]
    assert sent[0].name == "Renamed"
    state.save_subject_state.assert_awaited_once()
    assert state.save_subject_state.await_args.args[0] == "Math"
    state.clear_session.assert_called_once_with(123)


class TestUploadHelpers:
    def _rec(self, **kw):
        base = dict(
            name="lec.mp4",
            size_mb=10.0,
            created="2024-06-15",
            time="10:30",
            duration_ms=0,
            drive_id="d",
            item_id="i",
            team_name="T",
            subject_name="Math",
            is_video=True,
        )
        base.update(kw)
        return Recording(**base)

    def test_collect_selected_stable_and_bounded(self):
        from teamsleech.tg_bot.handlers.upload_ui import collect_selected

        session = MagicMock()
        session.pending_recordings = [self._rec(name="a"), self._rec(name="b")]
        session.selected_indices = {1, 5, 0}
        pairs = collect_selected(session)
        assert [i for i, _ in pairs] == [0, 1]

    def test_apply_rename_does_not_mutate(self):
        from teamsleech.tg_bot.handlers.upload_ui import apply_rename_overrides

        rec = self._rec(name="orig.mp4")
        out = apply_rename_overrides([(0, rec)], {0: "new.mp4"})
        assert out[0].name == "new.mp4"
        assert rec.name == "orig.mp4"

    def test_parse_recording_date_variants(self):
        from teamsleech.tg_bot.handlers.upload_ui import parse_recording_date

        assert parse_recording_date(self._rec(time="10:30")).strftime("%H:%M") == "10:30"
        assert parse_recording_date(self._rec(time="10:30:45")).strftime("%H:%M:%S") == "10:30:45"
        assert parse_recording_date(self._rec(time="")).strftime("%H:%M") == "00:00"
        none_time = self._rec(time="")
        none_time.time = None
        assert parse_recording_date(none_time).strftime("%H:%M") == "00:00"
        bad = self._rec(created="not-a-date")
        assert parse_recording_date(bad) is None

    def test_build_upload_summary(self):
        from teamsleech.tg_bot.handlers.upload_ui import build_upload_summary

        text = build_upload_summary([{"success": True}, {"success": False}])
        assert "1 succeeded" in text and "1 failed" in text

    async def test_commit_batches_and_preserves_cursor_on_bad_date(self):
        from teamsleech.tg_bot.handlers.upload_ui import commit_upload_results

        state = MagicMock()
        state.save_subject_state = AsyncMock()
        results = [
            {"success": True, "rec": self._rec(subject_name="Math", created="2024-06-15")},
            {"success": True, "rec": self._rec(subject_name="Math", created="2024-06-16")},
            {"success": True, "rec": self._rec(subject_name="Phys", created="bad-date")},
            {"success": False, "rec": self._rec(subject_name="Math")},
        ]
        await commit_upload_results(state, results)
        assert state.save_subject_state.await_count == 2
        math_call = [c for c in state.save_subject_state.await_args_list if c.args[0] == "Math"][0]
        assert math_call.args[1].date().isoformat() == "2024-06-16"
        assert math_call.args[2] == 2
        phys_call = [c for c in state.save_subject_state.await_args_list if c.args[0] == "Phys"][0]
        assert phys_call.args[1] is None
        assert phys_call.args[2] == 1

    async def test_progress_cb_handles_none_text(self):
        from teamsleech.tg_bot.handlers.upload_ui import make_transfer_progress_cb

        msg = AsyncMock()
        msg.text = None
        cb = make_transfer_progress_cb(msg, 2)
        await cb("error", {"name": "a.mp4", "error": "boom"})
        sent = msg.edit_text.await_args.args[0]
        assert not sent.startswith("None")
