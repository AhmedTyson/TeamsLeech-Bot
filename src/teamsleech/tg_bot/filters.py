from typing import Any

from pyrogram import filters

from teamsleech.core.config import settings


async def _owner_check(_: Any, __: Any, msg_or_cb: Any) -> bool:
    # Depending on whether it's a Message or CallbackQuery
    chat = getattr(msg_or_cb, "chat", None)
    if chat is None:
        nested = getattr(msg_or_cb, "message", None)
        chat = getattr(nested, "chat", None) if nested is not None else None

    if chat is None:
        return False

    return bool(chat.id == settings.telegram_chat_id)


owner_only = filters.create(_owner_check)
