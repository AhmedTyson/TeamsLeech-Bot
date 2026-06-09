import json
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from tg_bot.filters import owner_only
from services.discovery import DiscoveryService
from services.state import StateManager
from services.auth import rotate_github_secret
from models.domain import SubjectConfig

def register_search_inputs(app: Client, discovery: DiscoveryService, state: StateManager):
    
    async def is_searching(_, __, message: Message):
        session = state.get_session(message.chat.id)
        return session.is_searching_teams or session.pending_add_step != ""

    search_filter = filters.create(is_searching)

    @app.on_message(filters.text & filters.private & owner_only & search_filter, group=0)
    async def handle_search_input(client: Client, message: Message):
        text = message.text.strip()
        chat_id = message.chat.id
        session = state.get_session(chat_id)
        
        if text.lower() == "cancel":
            session.is_searching_teams = False
            session.pending_add_step = ""
            session.pending_add_team = None
            session.pending_add_data.clear()
            await message.reply("❌ Subject setup cancelled.")
            return

        # Handle Interactive Setup Flow
        if session.pending_add_step == "ask_name":
            session.pending_add_data["name"] = text
            session.pending_add_step = "ask_short"
            await message.reply("📝 Got it.\n\nNow, send a **Short Name** (e.g., `DB` for Database).")
            return
            
        if session.pending_add_step == "ask_short":
            session.pending_add_data["short"] = text
            session.pending_add_step = "ask_doctor"
            await message.reply("👨‍🏫 Almost done.\n\nSend the **Doctor's Name** (e.g., `Dr. Ahmed`), or type `skip` if you don't want to add one.")
            return
            
        if session.pending_add_step == "ask_doctor":
            doc = "" if text.lower() == "skip" else text
            session.pending_add_data["doctor"] = doc
            
            # We have all data! Let's build the config and update GitHub.
            team = session.pending_add_team
            new_subject = SubjectConfig(
                name=session.pending_add_data["name"],
                short=session.pending_add_data["short"],
                doctor=doc,
                keywords=[team.display_name] # Add the team's display name as the keyword!
            )
            
            await message.reply(f"⏳ Saving `{new_subject.name}` to GitHub Secrets...")
            
            # Load existing subjects
            from services.scanner import ScannerService
            scanner = ScannerService(discovery.graph, state)
            existing = scanner.load_subjects()
            
            # Append and save
            existing.append(new_subject)
            json_str = json.dumps({"subjects": [s.model_dump() for s in existing]}, indent=2)
            
            try:
                await rotate_github_secret("SUBJECTS_JSON", json_str)
                # Also update local environment so it reflects immediately
                import os
                from core.config import settings
                os.environ["SUBJECTS_JSON"] = json_str
                settings.subjects_json = json_str
                
                await message.reply(f"✅ Success! **{new_subject.name}** is now permanently configured and will be tracked automatically.")
            except Exception as e:
                await message.reply(f"❌ Failed to save to GitHub Secrets: {e}\n\nMake sure your GH_PAT is valid.")
                
            # Clear state
            session.is_searching_teams = False
            session.pending_add_step = ""
            session.pending_add_team = None
            session.pending_add_data.clear()
            return

        # Normal Search Flow
        await message.reply(f"🔍 Searching for '{text}'...")
        is_valid, msg, matched_teams = await discovery.search_teams(text)
        
        if not is_valid:
            await message.reply(msg)
            return
            
        if not matched_teams:
            await message.reply(msg + "\nTry a different keyword or `cancel`.")
            return
            
        # Build inline keyboard to let user add the team
        buttons = []
        for t in matched_teams:
            # We must shorten the callback data because Telegram limits it to 64 bytes
            short_id = t.id[:30] # Just pass the first 30 chars of the id or something? 
            # Or better, save the matched teams in session so we can look them up by index
            buttons.append([InlineKeyboardButton(f"➕ Add {t.display_name[:20]}...", callback_data=f"add_team:{t.id}")])
            
        # Store temporary matched teams in session
        # For simplicity, we just use the ID in callback
        session.pending_add_data["last_search_results"] = json.dumps([t.model_dump() for t in matched_teams])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply(msg + "\n\n_Tap a team below to configure it, or type a new keyword to search again._", reply_markup=reply_markup)

    @app.on_callback_query(filters.regex(r"^add_team:") & owner_only)
    async def handle_add_team(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        team_id = cb.data.split(":", 1)[1]
        
        # Look up the team from our last search
        import json
        last_results = json.loads(session.pending_add_data.get("last_search_results", "[]"))
        team_dict = next((t for t in last_results if t["id"] == team_id), None)
        
        if not team_dict:
            await cb.answer("Team not found or search expired.", show_alert=True)
            return
            
        from models.domain import Team
        team = Team(**team_dict)
        
        session.pending_add_team = team
        session.pending_add_step = "ask_name"
        
        await cb.message.edit_text(f"✅ Selected: **{team.display_name}**\n\nLet's configure it.\nFirst, send the **Official Subject Name** (e.g., `Database Systems`).\n\n_Type `cancel` to exit._")
        await cb.answer()
