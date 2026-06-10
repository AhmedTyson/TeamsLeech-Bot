from pyrogram import filters

from teamsleech.core.config import settings


async def _owner_check(_, __, msg_or_cb):
    # Depending on whether it's a Message or CallbackQuery
    chat = getattr(msg_or_cb, "chat", None)
    if not chat:
        chat = getattr(msg_or_cb.message, "chat", None)
    
    if not chat:
        return False
        
    return chat.id == settings.telegram_chat_id

owner_only = filters.create(_owner_check)
