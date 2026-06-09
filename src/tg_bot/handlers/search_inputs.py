from pyrogram import Client, filters
from pyrogram.types import Message

from tg_bot.filters import owner_only
from services.discovery import DiscoveryService
from services.state import StateManager

def register_search_inputs(app: Client, discovery: DiscoveryService, state: StateManager):
    
    async def is_searching(_, __, message: Message):
        session = state.get_session(message.chat.id)
        return session.is_searching_teams

    search_filter = filters.create(is_searching)

    @app.on_message(filters.text & filters.private & owner_only & search_filter)
    async def handle_search_input(client: Client, message: Message):
        text = message.text.strip()
        chat_id = message.chat.id
        
        if text.lower() == "cancel":
            session = state.get_session(chat_id)
            session.is_searching_teams = False
            await message.reply("❌ Search mode cancelled.")
            return

        await message.reply(f"🔍 Searching for '{text}'...")
        
        is_valid, msg, matched_teams = await discovery.search_teams(text)
        
        if not is_valid:
            await message.reply(msg)
            return
            
        if not matched_teams:
            await message.reply(msg + "\nTry a different keyword or `cancel`.")
            return
            
        reply_text = msg + "\n\n"
        for t in matched_teams:
            reply_text += f"• `{t.display_name}`\n"
            
        reply_text += "\n_Copy the exact name above to your `subjects_config.json` to track it!_"
        reply_text += "\n_Type another keyword to search again, or `cancel`._"
        
        await message.reply(reply_text)
