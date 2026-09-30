"""Flow coverage for Telegram handler closures (search/rename/date/select)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from teamsleech.models.domain import SubjectConfig, Team


def _capture_app():
    app = MagicMock()
    handlers = {}

    def _collect(func):
        handlers.setdefault(func.__name__, func)
        return func

    app.on_callback_query.side_effect = lambda *a, **k: _collect
    app.on_message.side_effect = lambda *a, **k: _collect
    return app, handlers, handlers


def _client():
    client = MagicMock()
    client.send_message = AsyncMock()
    return client


def _cb(data, chat_id=123):
    cb = AsyncMock()
    cb.data = data
    cb.message = AsyncMock()
    cb.message.chat.id = chat_id
    return cb


def _msg(text, chat_id=123):
    m = AsyncMock()
    m.text = text
    m.chat.id = chat_id
    m.continue_propagation = MagicMock()
    return m


def _session(**kw):
    s = MagicMock()
    s.pending_recordings = []
    s.selected_indices = set()
    s.rename_overrides = {}
    s.pending_add_data = {}
    s.is_searching_teams = False
    s.pending_add_step = ""
    s.pending_add_team = None
    s.pending_rename_idx = None
    s.pending_suggestion = None
    s.date_input_pending = False
    s.subject_filter = None
    s.scan_label = ""
    s.scan_in_progress = False
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _rec(name="lec.mp4", subject="Math", **kw):
    from teamsleech.models.domain import Recording

    base = dict(
        name=name,
        size_mb=10.0,
        created="2024-06-15",
        time="10:30",
        duration_ms=0,
        drive_id="d",
        item_id="i",
        team_name="T",
        subject_name=subject,
        is_video=True,
    )
    base.update(kw)
    return Recording(**base)


def _register_search(monkeypatch=None):
    from teamsleech.tg_bot.handlers.search_inputs import register_search_inputs

    discovery = MagicMock()
    discovery.search_teams = AsyncMock(return_value=(True, "none", []))
    session = _session(is_searching_teams=True)
    state = MagicMock()
    state.get_session.return_value = session
    app, cbs, msgs = _capture_app()
    register_search_inputs(app, discovery, state)
    return cbs, msgs, discovery, state, session


class TestSearchWizardFlow:
    async def test_cancel_clears(self):
        cbs, _, _, _, session = _register_search()
        session.pending_add_data["x"] = "y"
        await cbs["handle_search_input"](MagicMock(), _msg("cancel"))
        assert session.is_searching_teams is False
        assert session.pending_add_data == {}

    async def test_ask_name_advances(self):
        cbs, _, _, _, session = _register_search()
        session.pending_add_step = "ask_name"
        client = MagicMock()
        client.reply = AsyncMock()
        msg = _msg("Math Dept")
        await cbs["handle_search_input"](client, msg)
        assert session.pending_add_step == "ask_short"
        assert session.pending_add_data["name"] == "Math Dept"

    async def test_ask_short_advances(self):
        cbs, _, _, _, session = _register_search()
        session.pending_add_step = "ask_short"
        await cbs["handle_search_input"](MagicMock(), _msg("MTH"))
        assert session.pending_add_step == "ask_doctor"

    async def test_ask_doctor_saves(self, monkeypatch):
        from teamsleech.core.config import settings

        cbs, _, discovery, _, session = _register_search()
        monkeypatch.setattr(settings, "subjects_json", "")
        monkeypatch.setattr(settings, "subjects_path", "/dev/null/subjects.json")
        session.pending_add_step = "ask_doctor"
        session.pending_add_team = Team(id="t1", display_name="Math Group")
        session.pending_add_data.update({"name": "Math", "short": "MTH"})
        rotate = AsyncMock()
        with patch(
            "teamsleech.tg_bot.handlers.search_inputs.rotate_github_secret",
            new=rotate,
        ):
            msg = _msg("skip")
            await cbs["handle_search_input"](MagicMock(), msg)
        rotate.assert_awaited_once()
        assert session.is_searching_teams is False
        assert session.pending_add_data == {}
        msg.reply.assert_called()
        assert "Success" in msg.reply.await_args.args[0]

    async def test_keyword_search_lists_teams(self):
        cbs, _, discovery, _, session = _register_search()
        discovery.search_teams = AsyncMock(
            return_value=(True, "found", [Team(id="t1", display_name="Math Group")])
        )
        msg = _msg("math")
        await cbs["handle_search_input"](MagicMock(), msg)
        assert "last_search_results" in session.pending_add_data
        msg.reply.assert_called()

    async def test_short_keyword_rejected(self):
        cbs, _, discovery, _, _ = _register_search()
        discovery.search_teams = AsyncMock(return_value=(False, "too short", []))
        msg = _msg("ab")
        await cbs["handle_search_input"](MagicMock(), msg)
        msg.reply.assert_called_with("too short")

    async def test_yield_propagates_to_rename(self):
        cbs, _, _, _, session = _register_search()
        session.pending_rename_idx = 0
        msg = _msg("New Name")
        await cbs["handle_search_input"](MagicMock(), msg)
        msg.continue_propagation.assert_called_once()
        msg.reply.assert_not_called()

    async def test_search_page_expired(self):
        cbs, _, _, _, _ = _register_search()
        cb = _cb("srch_pg:0")
        await cbs["handle_search_page"](MagicMock(), cb)
        cb.answer.assert_awaited()

    async def test_search_page_renders(self):
        cbs, _, _, _, session = _register_search()
        session.pending_add_data["last_search_results"] = json.dumps(
            [Team(id="t1", display_name="Math Group").model_dump()]
        )
        cb = _cb("srch_pg:0")
        await cbs["handle_search_page"](MagicMock(), cb)
        cb.answer.assert_awaited()

    async def test_del_subj_invalid(self, monkeypatch):
        from teamsleech.core.config import settings

        cbs, _, _, _, _ = _register_search()
        monkeypatch.setattr(settings, "subjects_json", "")
        monkeypatch.setattr(settings, "subjects_path", "/dev/null/subjects.json")
        cb = _cb("del_subj:5")
        await cbs["handle_del_subj"](MagicMock(), cb)
        cb.answer.assert_awaited()

    async def test_del_flow_confirm_and_execute(self, monkeypatch):
        from teamsleech.core.config import settings

        cbs, _, _, _, _ = _register_search()
        monkeypatch.setattr(
            settings,
            "subjects_json",
            json.dumps({"subjects": [{"name": "Math", "keywords": ["math"]}]}),
        )
        cb = _cb("del_subj:0")
        await cbs["handle_del_subj"](MagicMock(), cb)
        assert "Delete subject" in cb.message.edit_text.await_args.args[0]

        rotate = AsyncMock()
        with patch(
            "teamsleech.tg_bot.handlers.search_inputs.rotate_github_secret",
            new=rotate,
        ):
            cb2 = _cb("del_confirm:0")
            await cbs["handle_del_confirm"](MagicMock(), cb2)
        rotate.assert_awaited_once()

    async def test_del_cancel(self):
        cbs, _, _, _, _ = _register_search()
        cb = _cb("del_cancel")
        await cbs["handle_del_cancel"](MagicMock(), cb)
        cb.answer.assert_awaited()

    async def test_add_team_invalid_id(self):
        cbs, _, _, _, _ = _register_search()
        cb = _cb("add_team:has:colon")
        await cbs["handle_add_team"](MagicMock(), cb)
        cb.answer.assert_awaited()

    async def test_add_team_starts_wizard(self):
        cbs, _, _, _, session = _register_search()
        team = Team(id="t1", display_name="Math Group")
        session.pending_add_data["last_search_results"] = json.dumps([team.model_dump()])
        cb = _cb("add_team:t1")
        await cbs["handle_add_team"](MagicMock(), cb)
        assert session.pending_add_step == "ask_name"
        assert session.pending_add_team == team


def _register_upload(session=None, transfer=None, scanner=None):
    from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui

    state = MagicMock()
    state.get_session.return_value = session or _session()
    transfer = transfer or MagicMock()
    scanner = scanner or MagicMock()
    scanner.load_subjects.return_value = []
    app, cbs, msgs = _capture_app()
    register_upload_ui(app, transfer, state, scanner)
    return cbs, msgs, transfer, state


class TestUploadSelections:
    async def test_select_toggle(self):
        session = _session(pending_recordings=[_rec("a"), _rec("b")])
        cbs, _, _, state = _register_upload(session=session)
        await cbs["handle_select"](MagicMock(), _cb("sel:0"))
        assert session.selected_indices == {0}
        await cbs["handle_select"](MagicMock(), _cb("sel:0"))
        assert session.selected_indices == set()
        state.get_session.assert_called()

    async def test_select_all_toggle(self):
        session = _session(pending_recordings=[_rec("a"), _rec("b")])
        cbs, _, _, _ = _register_upload(session=session)
        await cbs["handle_select"](MagicMock(), _cb("sel:all"))
        assert session.selected_indices == {0, 1}
        await cbs["handle_select"](MagicMock(), _cb("sel:all"))
        assert session.selected_indices == set()

    async def test_select_pdfs_and_videos(self):
        session = _session(
            pending_recordings=[
                _rec("a.mp4", is_video=True),
                _rec("b.pdf", is_video=False),
            ]
        )
        cbs, _, _, _ = _register_upload(session=session)
        await cbs["handle_select_pdfs"](MagicMock(), _cb("sel:pdfs"))
        assert session.selected_indices == {1}
        await cbs["handle_select_videos"](MagicMock(), _cb("sel:videos"))
        assert session.selected_indices == {0}

    async def test_cancel_clears_session(self):
        session = _session()
        cbs, _, _, state = _register_upload(session=session)
        await cbs["handle_cancel"](MagicMock(), _cb("cancel:check"))
        state.clear_session.assert_called_once()


class TestRenameFlow:
    def _regs(self, session=None, subjects=None):
        session = session or _session(pending_recordings=[_rec("orig.mp4")])
        scanner = MagicMock()
        scanner.load_subjects.return_value = subjects or []
        state = MagicMock()
        state.get_session.return_value = session
        state.get_last_lecture.return_value = 5
        return session, scanner, state

    async def test_rename_btn_without_suggestion(self):
        from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui

        session, scanner, state = self._regs()
        app, cbs, _ = _capture_app()
        register_upload_ui(app, MagicMock(), state, scanner)
        cb = _cb("ren:0")
        await cbs["handle_rename_btn"](MagicMock(), cb)
        assert session.pending_rename_idx == 0
        cb.message.reply.assert_called()

    async def test_rename_btn_with_suggestion(self):
        from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui

        session, scanner, state = self._regs(
            subjects=[SubjectConfig(name="Math", short="M", doctor="Dr", keywords=["m"])]
        )
        app, cbs, _ = _capture_app()
        register_upload_ui(app, MagicMock(), state, scanner)
        cb = _cb("ren:0")
        await cbs["handle_rename_btn"](MagicMock(), cb)
        assert session.pending_suggestion == "M - L6 - Dr"

    async def test_accept_suggestion(self):
        from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui

        session = _session(
            pending_recordings=[_rec("orig.mp4")],
            pending_rename_idx=0,
            pending_suggestion="M - L6",
        )
        state = MagicMock()
        state.get_session.return_value = session
        app, cbs, _ = _capture_app()
        register_upload_ui(app, MagicMock(), state, MagicMock())
        cb = _cb("sug:0")
        await cbs["handle_accept_suggestion"](MagicMock(), cb)
        assert session.rename_overrides[0] == "M - L6"
        assert session.pending_rename_idx is None

    async def test_accept_suggestion_mismatch(self):
        from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui

        session = _session(pending_recordings=[_rec("orig.mp4")])
        state = MagicMock()
        state.get_session.return_value = session
        app, cbs, _ = _capture_app()
        register_upload_ui(app, MagicMock(), state, MagicMock())
        cb = _cb("sug:0")
        await cbs["handle_accept_suggestion"](MagicMock(), cb)
        cb.answer.assert_awaited()
        assert session.rename_overrides == {}

    async def test_rename_input_saves(self):
        from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui

        session = _session(pending_recordings=[_rec("orig.mp4")], pending_rename_idx=0)
        state = MagicMock()
        state.get_session.return_value = session
        app, _, msgs = _capture_app()
        register_upload_ui(app, MagicMock(), state, MagicMock())
        msg = _msg("My Name")
        await msgs["handle_rename_input"](MagicMock(), msg)
        assert session.rename_overrides[0] == "My Name"
        assert session.pending_rename_idx is None

    async def test_rename_input_stale_index(self):
        from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui

        session = _session(pending_recordings=[], pending_rename_idx=4)
        state = MagicMock()
        state.get_session.return_value = session
        app, _, msgs = _capture_app()
        register_upload_ui(app, MagicMock(), state, MagicMock())
        msg = _msg("My Name")
        await msgs["handle_rename_input"](MagicMock(), msg)
        assert session.pending_rename_idx is None
        msg.reply.assert_called()

    async def test_rename_input_idle_propagates(self):
        from teamsleech.tg_bot.handlers.upload_ui import register_upload_ui

        session = _session()
        state = MagicMock()
        state.get_session.return_value = session
        app, _, msgs = _capture_app()
        register_upload_ui(app, MagicMock(), state, MagicMock())
        msg = _msg("hello")
        await msgs["handle_rename_input"](MagicMock(), msg)
        msg.continue_propagation.assert_called_once()


def _register_scanner(session=None, scan_result=None):
    from teamsleech.tg_bot.handlers.scanner_ui import register_scanner_ui

    scanner = MagicMock()
    scanner.scan_recordings = AsyncMock(return_value=scan_result or {})
    state = MagicMock()
    state.get_session.return_value = session or _session()
    app, cbs, msgs = _capture_app()
    register_scanner_ui(app, scanner, state)
    return cbs, msgs, scanner, state


class TestScannerFlows:
    async def test_subject_select_starts_date_wizard(self):
        session = _session()
        cbs, _, _, _ = _register_scanner(session=session)
        await cbs["handle_subject_select"](MagicMock(), _cb("subj:Math"))
        assert session.date_input_pending is True
        assert session.subject_filter == "Math"
        assert session.is_searching_teams is False

    async def test_date_btn_all_scans(self):
        session = _session(date_input_pending=True, subject_filter="Math")
        cbs, _, scanner, _ = _register_scanner(session=session)
        await cbs["handle_date_btn"](_client(), _cb("date_btn:all"))
        scanner.scan_recordings.assert_awaited_once_with("Math", None, None)

    async def test_date_btn_expired(self):
        session = _session(date_input_pending=False)
        cbs, _, scanner, _ = _register_scanner(session=session)
        await cbs["handle_date_btn"](MagicMock(), _cb("date_btn:today"))
        scanner.scan_recordings.assert_not_called()

    async def test_date_change_reopens(self):
        session = _session()
        cbs, _, _, _ = _register_scanner(session=session)
        await cbs["handle_date_change"](MagicMock(), _cb("date:change"))
        assert session.date_input_pending is True

    async def test_date_input_invalid(self):
        session = _session(date_input_pending=True)
        cbs, msgs, scanner, _ = _register_scanner(session=session)
        msg = _msg("not a date")
        await msgs["handle_date_input"](MagicMock(), msg)
        scanner.scan_recordings.assert_not_called()
        msg.reply.assert_called()

    async def test_date_input_cancel(self):
        session = _session(date_input_pending=True, subject_filter="Math")
        cbs, msgs, scanner, _ = _register_scanner(session=session)
        await msgs["handle_date_input"](MagicMock(), _msg("cancel"))
        assert session.date_input_pending is False
        scanner.scan_recordings.assert_not_called()

    async def test_date_input_valid_scans(self):
        session = _session(date_input_pending=True, subject_filter="Math")
        cbs, msgs, scanner, _ = _register_scanner(session=session)
        await msgs["handle_date_input"](_client(), _msg("2026-04-01"))
        scanner.scan_recordings.assert_awaited_once_with("Math", "2026-04-01", None)
