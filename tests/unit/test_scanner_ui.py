from unittest.mock import AsyncMock, MagicMock

import pytest

from teamsleech.models.domain import Recording
from teamsleech.tg_bot.handlers.scanner_ui import (
    _parse_date_input,
    _validate_date_range,
    register_scanner_ui,
)


@pytest.fixture
def mock_scanner():
    scanner = MagicMock()
    scanner.scan_recordings = AsyncMock()
    scanner.scan_recordings.return_value = {
        "Math": [
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
    }
    return scanner


@pytest.fixture
def mock_state():
    state = MagicMock()
    session_mock = MagicMock()
    session_mock.pending_recordings = []
    session_mock.selected_indices = set()
    session_mock.scan_in_progress = False
    state.get_session.return_value = session_mock
    return state


async def test_subject_all_reports_no_files(mock_scanner, mock_state):
    mock_scanner.scan_recordings = AsyncMock(return_value={})
    handlers_cb = {}
    mock_client = MagicMock()
    mock_client.send_message = AsyncMock()
    mock_client.on_callback_query.side_effect = lambda *a, **k: (
        lambda f: handlers_cb.setdefault(f.__name__, f)
    )
    mock_client.on_message.side_effect = lambda *a, **k: lambda f: f
    register_scanner_ui(mock_client, mock_scanner, mock_state)

    cb = AsyncMock()
    cb.data = "subj:__ALL__"
    cb.message = AsyncMock()
    cb.message.chat.id = 123
    await handlers_cb["handle_subject_select"](mock_client, cb)

    mock_scanner.scan_recordings.assert_awaited_once_with(None, None, None)
    sent = mock_client.send_message.await_args.args[1]
    assert "No new files" in sent


async def test_scan_error_surfaced_to_chat(mock_state):
    scanner = MagicMock()
    scanner.scan_recordings = AsyncMock(side_effect=RuntimeError("graph down"))
    handlers_cb = {}
    mock_client = MagicMock()
    mock_client.send_message = AsyncMock()
    mock_client.on_callback_query.side_effect = lambda *a, **k: (
        lambda f: handlers_cb.setdefault(f.__name__, f)
    )
    mock_client.on_message.side_effect = lambda *a, **k: lambda f: f
    register_scanner_ui(mock_client, scanner, mock_state)

    cb = AsyncMock()
    cb.data = "subj:__ALL__"
    cb.message = AsyncMock()
    cb.message.chat.id = 123
    await handlers_cb["handle_subject_select"](mock_client, cb)

    sent = mock_client.send_message.await_args.args[1]
    assert "Fetch error" in sent


async def test_untracked_teams_appended_to_message():
    from teamsleech.models.domain import Team

    scanner = MagicMock()
    scanner.scan_recordings = AsyncMock(return_value={})
    scanner.last_unmatched = [Team(id="9", display_name="free_group")]
    state = MagicMock()
    session = MagicMock()
    session.pending_recordings = []
    session.selected_indices = set()
    session.scan_in_progress = False
    state.get_session.return_value = session
    app = MagicMock()
    cbs = {}
    app.on_callback_query.side_effect = lambda *a, **k: lambda f: cbs.setdefault(f.__name__, f)
    app.on_message.side_effect = lambda *a, **k: lambda f: f
    register_scanner_ui(app, scanner, state)
    client = MagicMock()
    client.send_message = AsyncMock()
    cb = AsyncMock()
    cb.data = "subj:__ALL__"
    cb.message = AsyncMock()
    cb.message.chat.id = 123
    await cbs["handle_subject_select"](client, cb)
    sent = client.send_message.await_args.args[1]
    assert "not tracked by any subject" in sent
    assert "free\\_group" in sent


class TestValidateDateRange:
    def test_valid_single_day(self):
        ok, _ = _validate_date_range("2026-04-01", "2026-04-01")
        assert ok

    def test_valid_range(self):
        ok, _ = _validate_date_range("2026-04-01", "2026-04-07")
        assert ok

    def test_rejects_inverted(self):
        ok, msg = _validate_date_range("2026-04-07", "2026-04-01")
        assert not ok and "before" in msg

    def test_rejects_over_30_days(self):
        ok, msg = _validate_date_range("2020-01-01", "2020-03-15")
        assert not ok and "30" in msg

    def test_rejects_bad_format(self):
        ok, _ = _validate_date_range("2026-13-99", "2026-13-99")
        assert not ok


class TestParseDateInput:
    def test_range_to_and_dash(self):
        assert _parse_date_input("2026-04-01 to 2026-04-07")[:2] == ("2026-04-01", "2026-04-07")
        assert _parse_date_input("2026-04-01 - 2026-04-07")[:2] == ("2026-04-01", "2026-04-07")
        assert _parse_date_input("2026-04-01-2026-04-07")[:2] == ("2026-04-01", "2026-04-07")

    def test_single_date(self):
        ds, de, _ = _parse_date_input("2026-04-01")
        assert (ds, de) == ("2026-04-01", None)

    def test_month_year_bounds(self):
        assert _parse_date_input("jan 99999999") is None
        assert _parse_date_input("jan 1999") is None
        assert _parse_date_input("march 2026") is not None


async def test_concurrent_scans_single_flight():
    import asyncio

    from teamsleech.services.state import StateManager

    release = asyncio.Event()

    async def slow_scan(*args, **kwargs):
        await release.wait()
        return {}

    scanner = MagicMock()
    scanner.scan_recordings = AsyncMock(side_effect=slow_scan)
    state = StateManager(MagicMock(), 999)
    session = state.get_session(123)
    session.date_input_pending = True

    cbs = {}
    app = MagicMock()
    app.on_callback_query.side_effect = lambda *a, **k: lambda f: cbs.setdefault(f.__name__, f)
    app.on_message.side_effect = lambda *a, **k: lambda f: f
    register_scanner_ui(app, scanner, state)

    client = MagicMock()
    client.send_message = AsyncMock()

    def _cb(data):
        cb = AsyncMock()
        cb.data = data
        cb.message = AsyncMock()
        cb.message.chat.id = 123
        return cb

    t1 = asyncio.create_task(cbs["handle_date_btn"](client, _cb("date_btn:today")))
    await asyncio.sleep(0.2)
    assert session.scan_in_progress is True
    await cbs["handle_subject_select"](client, _cb("subj:__ALL__"))
    release.set()
    await asyncio.wait_for(t1, timeout=10)

    assert scanner.scan_recordings.await_count == 1
    assert session.scan_in_progress is False
    sent = [c.args[1] for c in client.send_message.await_args_list]
    assert any("already running" in str(s) for s in sent)
