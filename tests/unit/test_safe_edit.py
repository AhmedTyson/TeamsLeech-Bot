from unittest.mock import AsyncMock, patch

from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified

from teamsleech.tg_bot.handlers import safe_edit_text


async def test_none_message_ignored():
    await safe_edit_text(None, "hi")


async def test_success_edits_once():
    msg = AsyncMock()
    await safe_edit_text(msg, "hi", reply_markup="kb")
    msg.edit_text.assert_awaited_once_with("hi", reply_markup="kb")


async def test_not_modified_swallowed():
    msg = AsyncMock()
    msg.edit_text.side_effect = MessageNotModified("same")
    await safe_edit_text(msg, "hi")


async def test_invalid_id_swallowed():
    msg = AsyncMock()
    msg.edit_text.side_effect = MessageIdInvalid("gone")
    await safe_edit_text(msg, "hi")


async def test_flood_wait_retries_once():
    msg = AsyncMock()
    msg.edit_text.side_effect = [FloodWait(value=7), None]
    with patch("teamsleech.tg_bot.handlers.asyncio.sleep", new=AsyncMock()) as nap:
        await safe_edit_text(msg, "hi")
    nap.assert_awaited_once_with(7)
    assert msg.edit_text.await_count == 2


async def test_flood_wait_gives_up_after_retry():
    msg = AsyncMock()
    msg.edit_text.side_effect = FloodWait(value=1)
    with patch("teamsleech.tg_bot.handlers.asyncio.sleep", new=AsyncMock()):
        await safe_edit_text(msg, "hi")
    assert msg.edit_text.await_count == 2
