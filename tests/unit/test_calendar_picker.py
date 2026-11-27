from unittest.mock import AsyncMock, MagicMock

import pytest
from pyrogram.types import Chat

from teamsleech.models.domain import Recording
from teamsleech.tg_bot.handlers.scanner_ui import register_scanner_ui
from teamsleech.tg_bot.keyboards import build_calendar_keyboard


def _flat(kb):
    return [btn for row in kb.inline_keyboard for btn in row]


class TestBuildCalendarKeyboard:
    def test_month_structure(self):
        kb = build_calendar_keyboard(2026, 4)
        rows = kb.inline_keyboard
        header = rows[0]
        assert header[1].text == "April 2026"
        assert header[0].callback_data == "cal:nav:2026-03"
        assert header[2].callback_data == "cal:nav:2026-05"
        assert [b.text for b in rows[1]] == [
            "Mo", "Tu", "We", "Th", "Fr", "Sa", "Su",
        ]
        day_cells = {
            b.text: b.callback_data
            for b in _flat(kb)
            if b.callback_data.startswith("cal:day:")
        }
        assert day_cells["1"] == "cal:day:2026-04-01"
        assert day_cells["30"] == "cal:day:2026-04-30"
        assert "31" not in day_cells
        assert rows[-1][0].callback_data == "cal:cancel"

    def test_year_rollover(self):
        dec = build_calendar_keyboard(2026, 12)
        assert dec.inline_keyboard[0][2].callback_data == "cal:nav:2027-01"
        jan = build_calendar_keyboard(2026, 1)
        assert jan.inline_keyboard[0][0].callback_data == "cal:nav:2025-12"

    def test_picked_start_highlighted(self):
        kb = build_calendar_keyboard(2026, 4, picked_start="2026-04-15")
        marked = [
            b for b in _flat(kb)
            if b.callback_data == "cal:day:2026-04-15"
        ]
        assert marked[0].text == "•15•"


@pytest.fixture
def mock_scanner():
    scanner = MagicMock()
    scanner.scan_recordings = AsyncMock()
    scanner.scan_recordings.return_value = {
        "Math": [Recording(
            id="1", name="Vid1", url="http",
            is_video=True, size_mb=10.0,
            created="2026-04-01", team_name="T1",
            drive_id="d1", item_id="i1", subject_name="Math",
        )]
    }
    scanner.load_subjects.return_value = []
    return scanner


@pytest.fixture
def rig(mock_scanner):
    handlers = {}
    session = MagicMock()
    session.pending_recordings = []
    session.selected_indices = set()
    session.rename_overrides = {}
    session.triage_flags = {}
    session.subject_filter = "Math"
    session.date_input_pending = True
    session.cal_start = None

    state = MagicMock()
    state.get_session.return_value = session

    client = MagicMock()
    client.send_message = AsyncMock()

    def on_cb(*args, **kwargs):
        def wrapper(func):
            handlers[func.__name__] = func
            return func
        return wrapper

    client.on_callback_query.side_effect = on_cb
    client.on_message.side_effect = lambda *a, **k: (lambda f: f)

    register_scanner_ui(client, mock_scanner, state)
    return handlers, session, client, mock_scanner


def _cb(data):
    cb = AsyncMock()
    cb.data = data
    cb.message = AsyncMock()
    cb.message.chat = MagicMock(spec=Chat)
    cb.message.chat.id = 123
    return cb


@pytest.mark.asyncio
async def test_open_shows_calendar(rig):
    handlers, session, client, _ = rig
    cb = _cb("cal:open:2026-04")
    await handlers["handle_cal_open"](client, cb)
    kb = cb.message.edit_text.call_args.kwargs["reply_markup"]
    assert any(
        b.callback_data.startswith("cal:day:2026-04-") for b in _flat(kb)
    )
    assert session.cal_start is None


@pytest.mark.asyncio
async def test_nav_keeps_start(rig):
    handlers, session, client, _ = rig
    session.cal_start = "2026-04-10"
    cb = _cb("cal:nav:2026-05")
    await handlers["handle_cal_nav"](client, cb)
    kb = cb.message.edit_text.call_args.kwargs["reply_markup"]
    assert kb.inline_keyboard[0][1].text == "May 2026"
    assert session.cal_start == "2026-04-10"
    assert "end date" in cb.message.edit_text.call_args.args[0]


@pytest.mark.asyncio
async def test_first_pick_sets_start(rig):
    handlers, session, client, scanner = rig
    cb = _cb("cal:day:2026-04-10")
    await handlers["handle_cal_day"](client, cb)
    assert session.cal_start == "2026-04-10"
    scanner.scan_recordings.assert_not_called()
    kb = cb.message.edit_text.call_args.kwargs["reply_markup"]
    marked = [
        b for b in _flat(kb)
        if b.callback_data == "cal:day:2026-04-10"
    ]
    assert marked[0].text == "•10•"


@pytest.mark.asyncio
async def test_second_pick_runs_scan(rig):
    handlers, session, client, scanner = rig
    session.cal_start = "2026-04-10"
    cb = _cb("cal:day:2026-04-17")
    await handlers["handle_cal_day"](client, cb)
    scanner.scan_recordings.assert_awaited_once_with(
        "Math", "2026-04-10", "2026-04-17"
    )
    assert session.cal_start is None
    assert session.date_input_pending is False


@pytest.mark.asyncio
async def test_reversed_pick_swapped(rig):
    handlers, session, client, scanner = rig
    session.cal_start = "2026-04-17"
    cb = _cb("cal:day:2026-04-10")
    await handlers["handle_cal_day"](client, cb)
    scanner.scan_recordings.assert_awaited_once_with(
        "Math", "2026-04-10", "2026-04-17"
    )


@pytest.mark.asyncio
async def test_over_60_days_alerted_no_scan(rig):
    handlers, session, client, scanner = rig
    session.cal_start = "2026-01-01"
    cb = _cb("cal:day:2026-04-01")
    await handlers["handle_cal_day"](client, cb)
    scanner.scan_recordings.assert_not_called()
    assert cb.answer.call_args.kwargs.get("show_alert") is True
    assert session.cal_start == "2026-01-01"


@pytest.mark.asyncio
async def test_cancel_clears_state(rig):
    handlers, session, client, scanner = rig
    session.cal_start = "2026-04-10"
    cb = _cb("cal:cancel")
    await handlers["handle_cal_cancel"](client, cb)
    assert session.cal_start is None
    assert session.date_input_pending is False
    assert session.subject_filter is None
    scanner.scan_recordings.assert_not_called()


@pytest.mark.asyncio
async def test_noop_answers_only(rig):
    handlers, session, client, scanner = rig
    cb = _cb("cal:noop")
    await handlers["handle_cal_noop"](client, cb)
    cb.answer.assert_awaited_once()
    scanner.scan_recordings.assert_not_called()


@pytest.mark.asyncio
async def test_pick_dates_button_in_choice_keyboard(rig):
    handlers, session, client, _ = rig
    cb = _cb("date:change")
    await handlers["handle_date_change"](client, cb)
    kb = cb.message.edit_text.call_args.kwargs["reply_markup"]
    assert any(
        b.callback_data.startswith("cal:open:") for b in _flat(kb)
    )
