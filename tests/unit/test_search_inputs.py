from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from teamsleech.models.domain import Team
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.handlers.search_inputs import register_search_inputs


@pytest.fixture
def rig():
    app = MagicMock()
    handlers_msg = {}
    handlers_cb = {}

    def on_msg(*a, **k):
        def wrapper(func):
            handlers_msg[func.__name__] = func
            return func
        return wrapper

    def on_cb(*a, **k):
        def wrapper(func):
            handlers_cb[func.__name__] = func
            return func
        return wrapper

    app.on_message.side_effect = on_msg
    app.on_callback_query.side_effect = on_cb
    discovery = MagicMock()
    discovery.graph = MagicMock()
    state = StateManager(MagicMock(), 123)
    register_search_inputs(app, discovery, state)
    return app, handlers_msg, handlers_cb, discovery, state


def make_msg(text, state):
    msg = AsyncMock()
    msg.text = text
    msg.chat = MagicMock()
    msg.chat.id = 123
    return msg


async def send(rig, text):
    _, handlers_msg, _, _, state = rig
    session = state.get_session(123)
    msg = make_msg(text, state)
    await handlers_msg["handle_search_input"](MagicMock(), msg)
    return session, msg


class TestAddSteps:
    async def test_name_to_short(self, rig):
        _, _, _, _, state = rig
        session = state.get_session(123)
        session.is_searching_teams = True
        session.pending_add_step = "ask_name"
        session, msg = await send(rig, "Data Security")
        assert session.pending_add_step == "ask_short"
        assert session.pending_add_data["name"] == "Data Security"

    async def test_subj_kw_same_uses_team_name(self, rig):
        _, _, _, _, state = rig
        session = state.get_session(123)
        session.is_searching_teams = True
        session.pending_add_team = Team(id="t1", display_name="Data Security - Dr Hany")
        session.pending_add_step = "ask_subj_kw"
        session, _ = await send(rig, "same")
        assert session.pending_add_data["subj_kw"] == ["Data Security - Dr Hany"]
        assert session.pending_add_step == "ask_doc_kw"

    async def test_subj_kw_parsed(self, rig):
        _, _, _, _, state = rig
        session = state.get_session(123)
        session.is_searching_teams = True
        session.pending_add_team = Team(id="t1", display_name="Data Security - Dr Hany")
        session.pending_add_step = "ask_subj_kw"
        session, _ = await send(rig, "Data Security, DSEC")
        assert session.pending_add_data["subj_kw"] == ["Data Security", "DSEC"]
        assert session.pending_add_step == "ask_doc_kw"

    async def test_short_keywords_rejected(self, rig):
        _, _, _, _, state = rig
        session = state.get_session(123)
        session.is_searching_teams = True
        session.pending_add_team = Team(id="t1", display_name="Data Security - Dr Hany")
        session.pending_add_data["subj_kw"] = ["L4"]
        session.pending_add_step = "ask_doc_kw"
        session, msg = await send(rig, "skip")
        assert session.pending_add_step == "ask_subj_kw"
        assert "rejected" in msg.reply.await_args.args[0].lower()

    async def test_self_match_failure_returns_to_subj(self, rig):
        _, _, _, _, state = rig
        session = state.get_session(123)
        session.is_searching_teams = True
        session.pending_add_team = Team(id="t1", display_name="Math Group Alpha")
        session.pending_add_data["subj_kw"] = ["physics"]
        session.pending_add_step = "ask_doc_kw"
        session, msg = await send(rig, "skip")
        assert session.pending_add_step == "ask_subj_kw"
        assert "itself" in msg.reply.await_args.args[0]

    async def test_skip_skip_rejected(self, rig):
        _, _, _, _, state = rig
        session = state.get_session(123)
        session.is_searching_teams = True
        session.pending_add_step = "ask_doc_kw"
        session.pending_add_data["subj_kw"] = []
        session, msg = await send(rig, "skip")
        assert session.pending_add_step == "ask_subj_kw"
        assert "at least" in msg.reply.await_args.args[0].lower()

    async def test_full_flow_both_with_same_label(self, rig):
        _, _, _, _, state = rig
        session = state.get_session(123)
        session.is_searching_teams = True
        session.pending_add_team = Team(id="t1", display_name="Data Security - Dr Hany")
        session.pending_add_step = "ask_name"
        await send(rig, "Data Security")
        await send(rig, "DSEC")
        await send(rig, "Data Security")
        session, _ = await send(rig, "Hany, Gouda")
        assert session.pending_add_step == "ask_doc_label"
        with patch(
            "teamsleech.services.github_secrets.rotate_github_secret",
            AsyncMock(),
        ):
            session, msg = await send(rig, "same")
        assert session.pending_add_step == ""
        last_text = msg.reply.await_args_list[-1].args[0]
        assert "Hany + Gouda" not in last_text
        assert "doctor [Hany, Gouda]" in last_text

    async def test_subject_only_skips_label(self, rig):
        _, _, _, _, state = rig
        session = state.get_session(123)
        session.is_searching_teams = True
        session.pending_add_team = Team(id="t1", display_name="Data Security - Dr Hany")
        session.pending_add_step = "ask_name"
        await send(rig, "Data Security")
        await send(rig, "DSEC")
        await send(rig, "Data Security")
        with patch(
            "teamsleech.services.github_secrets.rotate_github_secret",
            AsyncMock(),
        ):
            session, msg = await send(rig, "skip")
        assert session.pending_add_step == ""
        assert "subject [Data Security]" in msg.reply.await_args_list[-1].args[0]

    async def test_cancel_clears(self, rig):
        _, _, _, _, state = rig
        session = state.get_session(123)
        session.is_searching_teams = True
        session.pending_add_step = "ask_doc_kw"
        session, msg = await send(rig, "cancel")
        assert session.pending_add_step == ""
        assert not session.is_searching_teams


def make_cb(data):
    cb = AsyncMock()
    cb.data = data
    cb.message = AsyncMock()
    cb.message.chat = MagicMock()
    cb.message.chat.id = 123
    return cb


class TestManage:
    def _seed(self, monkeypatch):
        import json

        from teamsleech.core.config import settings
        monkeypatch.setattr(
            settings,
            "subjects_json",
            json.dumps({"subjects": [
                {"name": "DS", "short": "D", "doctor": "Dr H",
                 "keywords": ["data"], "doctor_keywords": ["hany"]},
                {"name": "FT", "short": "F", "doctor": "",
                 "keywords": ["trade"], "doctor_keywords": []},
            ]}),
        )

    async def test_dashboard_lists_numbers(self, rig):
        from teamsleech.tg_bot.keyboards import build_manage_dashboard
        _, _, _, _, state = rig
        import json

        from teamsleech.core.config import settings
        settings.subjects_json = json.dumps({"subjects": [
            {"name": "DS", "short": "D", "keywords": ["data"]},
        ]})
        from teamsleech.services.scanner import ScannerService
        scanner = ScannerService(MagicMock(), state)
        text, markup = build_manage_dashboard(scanner.load_subjects())
        assert "1. **DS**" in text
        assert markup.inline_keyboard[0][0].callback_data == "mng:sel:0"

    async def test_select_shows_detail(self, rig, monkeypatch):
        _, _, handlers_cb, _, state = rig
        self._seed(monkeypatch)
        cb = make_cb("mng:sel:0")
        with patch(
            "teamsleech.tg_bot.handlers.search_inputs.safe_edit_text",
            AsyncMock(),
        ) as mock_edit:
            await handlers_cb["handle_manage"](MagicMock(), cb)
        text = mock_edit.await_args.args[1]
        assert "DS" in text and "Dr H" in text

    async def test_select_invalid_index(self, rig, monkeypatch):
        _, _, handlers_cb, _, state = rig
        self._seed(monkeypatch)
        cb = make_cb("mng:sel:9")
        await handlers_cb["handle_manage"](MagicMock(), cb)
        assert "changed" in cb.answer.await_args.args[0]

    async def test_edit_doctor_field_flow(self, rig, monkeypatch):
        _, handlers_msg, handlers_cb, _, state = rig
        self._seed(monkeypatch)
        cb = make_cb("mng:field:0:doctor")
        with patch(
            "teamsleech.tg_bot.handlers.search_inputs.safe_edit_text",
            AsyncMock(),
        ):
            await handlers_cb["handle_manage"](MagicMock(), cb)
        session = state.get_session(123)
        assert session.pending_edit_idx == 0
        assert session.pending_edit_field == "doctor"
        with patch(
            "teamsleech.services.github_secrets.rotate_github_secret",
            AsyncMock(),
        ):
            session, msg = await send(rig, "Dr New")
        assert session.pending_edit_idx is None
        assert "Updated" in msg.reply.await_args_list[0].args[0]

    async def test_delete_confirm_flow(self, rig, monkeypatch):
        _, _, handlers_cb, _, state = rig
        self._seed(monkeypatch)
        with patch(
            "teamsleech.tg_bot.handlers.search_inputs.safe_edit_text",
            AsyncMock(),
        ) as mock_edit:
            await handlers_cb["handle_manage"](MagicMock(), make_cb("mng:del:1"))
            assert "Delete **FT**" in mock_edit.await_args.args[1]
            with patch(
                "teamsleech.services.github_secrets.rotate_github_secret",
                AsyncMock(),
            ):
                await handlers_cb["handle_manage"](
                    MagicMock(), make_cb("mng:del_yes:1")
                )
            assert "Deleted **FT**" in mock_edit.await_args.args[1]
