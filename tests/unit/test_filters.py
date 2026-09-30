from unittest.mock import MagicMock

from teamsleech.tg_bot.filters import _owner_check


def _msg(chat_id):
    msg = MagicMock()
    msg.chat.id = chat_id
    return msg


async def test_owner_message_passes():
    from teamsleech.core.config import settings

    assert await _owner_check(None, None, _msg(settings.telegram_chat_id)) is True


async def test_stranger_message_rejected():
    assert await _owner_check(None, None, _msg(1)) is False


async def test_callback_query_uses_nested_chat():
    from teamsleech.core.config import settings

    cb = MagicMock(spec=["message"])
    cb.message.chat.id = settings.telegram_chat_id
    assert await _owner_check(None, None, cb) is True


async def test_no_chat_rejected():
    assert await _owner_check(None, None, object()) is False
