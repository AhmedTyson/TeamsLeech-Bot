"""Setup wizard: topics checklist, numbering picker, start handoff."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from teamsleech.models.domain import SubjectConfig
from teamsleech.tg_bot.handlers import setup_wizard
from teamsleech.tg_bot.handlers.setup_wizard import (
    build_numbering_text,
    build_topics_text,
    register_setup_wizard,
)


@pytest.fixture
def subjects():
    return [
        SubjectConfig(name="Math", short="M", topic_id=123, next_no=5),
        SubjectConfig(name="Physics", short="P", kind="section", next_no=1),
    ]


@pytest.fixture
def mock_scanner(subjects):
    scanner = MagicMock()
    scanner.load_subjects.return_value = subjects
    return scanner


@pytest.fixture
def handlers(mock_scanner):
    captured = {"msg": {}, "cb": {}}
    app = MagicMock()

    def on_message(*args, **kwargs):
        def wrapper(func):
            captured["msg"][func.__name__] = func
            return func
        return wrapper

    def on_callback_query(*args, **kwargs):
        def wrapper(func):
            captured["cb"][func.__name__] = func
            return func
        return wrapper

    app.on_message.side_effect = on_message
    app.on_callback_query.side_effect = on_callback_query
    register_setup_wizard(app, mock_scanner, MagicMock())
    return captured


@pytest.fixture(autouse=True)
def clean_pending():
    setup_wizard._pending.clear()
    yield
    setup_wizard._pending.clear()


def _cb(data, chat_id=1712494303):
    cb = MagicMock()
    cb.data = data
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.chat.id = chat_id
    cb.message.edit_text = AsyncMock()
    return cb


def test_topics_text_shows_status_and_copyable_commands(subjects):
    text = build_topics_text(subjects)
    assert "خطوة 1 من 3" in text
    assert "`/link M`" in text
    assert "`/link P`" in text
    assert "✅ مربوط" in text  # Math has topic_id
    assert "❌ لسه" in text  # Physics does not
    assert "مربوط 1 من 2" in text


def test_numbering_text_uses_prefix_and_value(subjects):
    text = build_numbering_text(subjects[1], 3, 1, 2)
    assert "Physics" in text
    assert "Sec03" in text
    assert "2 من 2" in text
    assert "لو الموضوع فاضي، سيبه 1" in text


@pytest.mark.asyncio
async def test_setup_entry_replies_with_checklist(handlers):
    msg = AsyncMock()
    await handlers["msg"]["handle_setup"](MagicMock(), msg)
    text = msg.reply.call_args[0][0]
    assert "ربط المواضيع" in text
    markup = msg.reply.call_args.kwargs["reply_markup"]
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert "🔄 تحديث" in labels
    assert "التالي ▶️" in labels


@pytest.mark.asyncio
async def test_refresh_edits_in_place(handlers):
    cb = _cb("wiz:refresh")
    await handlers["cb"]["handle_wiz_topics"](MagicMock(), cb)
    cb.message.edit_text.assert_awaited_once()
    assert "ربط المواضيع" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_tonum_zero_shows_first_subject(handlers):
    cb = _cb("wiz:tonum:0")
    await handlers["cb"]["handle_wiz_tonum"](MagicMock(), cb)
    text = cb.message.edit_text.call_args[0][0]
    assert "Math" in text
    assert "L05" in text  # current next_no as the default


@pytest.mark.asyncio
async def test_inc_dec_one_adjust_pending(handlers):
    client = MagicMock()
    cb = _cb("wiz:inc:0")
    await handlers["cb"]["handle_wiz_adjust"](client, cb)
    assert "L06" in cb.message.edit_text.call_args[0][0]
    cb = _cb("wiz:dec:0")
    await handlers["cb"]["handle_wiz_adjust"](client, cb)
    assert "L05" in cb.message.edit_text.call_args[0][0]
    cb = _cb("wiz:one:0")
    await handlers["cb"]["handle_wiz_adjust"](client, cb)
    assert "L01" in cb.message.edit_text.call_args[0][0]
    # dec never goes below 1
    cb = _cb("wiz:dec:0")
    await handlers["cb"]["handle_wiz_adjust"](client, cb)
    assert "L01" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_advance_persists_pending(handlers, subjects, monkeypatch):
    persist = AsyncMock()
    monkeypatch.setattr(
        "teamsleech.services.subjects_store.persist_subjects", persist
    )
    client = MagicMock()
    await handlers["cb"]["handle_wiz_adjust"](client, _cb("wiz:inc:0"))
    await handlers["cb"]["handle_wiz_tonum"](client, _cb("wiz:tonum:1"))
    persist.assert_awaited_once()
    assert subjects[0].next_no == 6
    assert subjects[1].next_no == 1


@pytest.mark.asyncio
async def test_last_advance_shows_ready(handlers, subjects, monkeypatch):
    monkeypatch.setattr(
        "teamsleech.services.subjects_store.persist_subjects", AsyncMock()
    )
    cb = _cb("wiz:tonum:2")
    await handlers["cb"]["handle_wiz_tonum"](MagicMock(), cb)
    text = cb.message.edit_text.call_args[0][0]
    assert "جاهزين" in text
    markup = cb.message.edit_text.call_args.kwargs["reply_markup"]
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert "🚀 ابدأ" in labels


@pytest.mark.asyncio
async def test_go_flushes_and_runs_missing_scan(handlers, subjects, monkeypatch):
    persist = AsyncMock()
    monkeypatch.setattr(
        "teamsleech.services.subjects_store.persist_subjects", persist
    )
    scan = AsyncMock()
    monkeypatch.setattr(
        "teamsleech.tg_bot.handlers.scanner_ui.run_missing_scan", scan
    )
    client = MagicMock()
    client.send_message = AsyncMock()
    await handlers["cb"]["handle_wiz_adjust"](client, _cb("wiz:inc:0"))
    cb = _cb("wiz:go")
    await handlers["cb"]["handle_wiz_go"](client, cb)
    persist.assert_awaited()
    assert subjects[0].next_no == 6
    scan.assert_awaited_once()
    # guidance message after the scan
    assert client.send_message.await_count == 1
    assert "Approve all" in client.send_message.call_args[0][1]


@pytest.mark.asyncio
async def test_cancel_clears_pending(handlers):
    client = MagicMock()
    cb = _cb("wiz:inc:0")
    await handlers["cb"]["handle_wiz_adjust"](client, cb)
    assert setup_wizard._pending
    cb = _cb("wiz:cancel")
    await handlers["cb"]["handle_wiz_cancel"](client, cb)
    assert not setup_wizard._pending
    assert "اتلغى" in cb.message.edit_text.call_args[0][0]


def test_parse_topic_link_two_and_three_segments():
    from teamsleech.tg_bot.handlers.setup_wizard import parse_topic_link

    assert parse_topic_link("https://t.me/c/4476745883/122") == (-1004476745883, 122)
    assert parse_topic_link("شوف https://t.me/c/4476745883/122/1305 كده") == (
        -1004476745883,
        122,
    )
    assert parse_topic_link("t.me/c/99/7") == (-10099, 7)
    assert parse_topic_link("https://t.me/somechannel/5") is None
    assert parse_topic_link("no link") is None


def test_pick_subject_keyboard_one_button_per_subject(subjects):
    from teamsleech.tg_bot.handlers.setup_wizard import (
        build_pick_subject_keyboard,
    )

    subjects[0].doctor = "Dr. A"
    kb = build_pick_subject_keyboard(subjects, -1004476745883, 122)
    rows = kb.inline_keyboard
    assert len(rows) == 3  # 2 subjects + cancel
    assert rows[0][0].text == "📚 Math — Dr. A"  # linked to 123, not 122
    assert rows[0][0].callback_data == "wiz:linkto:-1004476745883:122:0"
    assert rows[1][0].text == "📚 Physics"
    assert rows[1][0].callback_data == "wiz:linkto:-1004476745883:122:1"
    kb2 = build_pick_subject_keyboard(subjects, -1004476745883, 123)
    assert kb2.inline_keyboard[0][0].text == "📚 Math — Dr. A ✅"


@pytest.mark.asyncio
async def test_topic_link_paste_replies_with_picker(handlers):
    msg = AsyncMock()
    msg.text = "https://t.me/c/4476745883/122"
    await handlers["msg"]["handle_topic_link_paste"](MagicMock(), msg)
    text = msg.reply.call_args[0][0]
    assert "أنهي مادة" in text
    markup = msg.reply.call_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "wiz:linkto:-1004476745883:122:0" in datas
    assert "wiz:linkto:-1004476745883:122:1" in datas


@pytest.mark.asyncio
async def test_linkto_links_persists_and_confirms(
    handlers, subjects, monkeypatch
):
    persisted = {}

    async def fake_persist(subjs):
        persisted["done"] = True

    monkeypatch.setattr(
        "teamsleech.services.subjects_store.persist_subjects", fake_persist
    )

    async def fake_target(chat_id):
        persisted["target"] = chat_id

    monkeypatch.setattr(
        "teamsleech.tg_bot.handlers.commands.persist_target_chat_id", fake_target
    )
    client = MagicMock()
    member = MagicMock()
    member.status = "administrator"
    client.get_chat_member = AsyncMock(return_value=member)
    client.send_message = AsyncMock()

    cb = _cb("wiz:linkto:-1004476745883:122:1")
    await handlers["cb"]["handle_wiz_linkto"](client, cb)

    assert subjects[1].topic_id == 122
    assert persisted.get("done") is True
    assert persisted.get("target") == -1004476745883
    confirm = cb.message.edit_text.call_args[0][0]
    assert "اتربط" in confirm
    assert "Physics" in confirm
    assert "122" in confirm
    assert "أدمن" in confirm
    client.send_message.assert_awaited_once()
    assert "مربوط 2 من 2" in client.send_message.call_args[0][1]


@pytest.mark.asyncio
async def test_linkto_warns_when_bot_not_in_group(
    handlers, subjects, monkeypatch
):
    async def fake_persist(subjs):
        pass

    monkeypatch.setattr(
        "teamsleech.services.subjects_store.persist_subjects", fake_persist
    )

    async def fake_target(chat_id):
        pass

    monkeypatch.setattr(
        "teamsleech.tg_bot.handlers.commands.persist_target_chat_id", fake_target
    )
    client = MagicMock()
    client.get_chat_member = AsyncMock(side_effect=Exception("not participant"))
    client.send_message = AsyncMock()

    cb = _cb("wiz:linkto:-1004476745883:122:1")
    await handlers["cb"]["handle_wiz_linkto"](client, cb)
    confirm = cb.message.edit_text.call_args[0][0]
    assert "مش لاقي البوت" in confirm
