import json
import os

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from teamsleech.core.config import settings
from teamsleech.models.domain import SubjectConfig, Team
from teamsleech.services.auth import rotate_github_secret
from teamsleech.services.discovery import DiscoveryService
from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_edit_text


def _build_search_page(teams: list[Team], page: int) -> tuple[str, InlineKeyboardMarkup]:
    PAGE_SIZE = 5
    total_pages = max(1, (len(teams) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    page_teams = teams[start_idx:end_idx]
    
    text_lines = [f"🔍 Found {len(teams)} matching teams:\n", f"Page {page + 1} of {total_pages}:"]
    
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    
    buttons_row = []
    
    for i, t in enumerate(page_teams):
        num_str = number_emojis[i] if i < len(number_emojis) else f"{i+1}."
        text_lines.append(f"{num_str} {t.display_name}")
        buttons_row.append(
            InlineKeyboardButton(f"[ {i+1} ]", callback_data=f"add_team:{t.id}")
        )
        
    text_lines.append("\n_Tap a number below to configure that team_")
    text_lines.append("_or type a new keyword to search again._")
    
    keyboard = []
    if buttons_row:
        keyboard.append(buttons_row)
        
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"srch_pg:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"srch_pg:{page + 1}"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    return "\n".join(text_lines), InlineKeyboardMarkup(keyboard)

def register_search_inputs(
    app: Client, discovery: DiscoveryService, state: StateManager
):
    async def is_searching(_, __, message: Message):
        session = state.get_session(message.chat.id)
        return session.is_searching_teams or session.pending_add_step != ""

    search_filter = filters.create(is_searching)

    @app.on_message(
        filters.text & filters.private & owner_only & search_filter, group=0
    )
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

        if session.pending_add_step == "ask_name":
            session.pending_add_data["name"] = text
            session.pending_add_step = "ask_short"
            await message.reply(
                "📝 Got it.\n\n"
                "Now, send a **Short Name** (e.g., `DB` for Database)."
            )
            return

        if session.pending_add_step == "ask_short":
            session.pending_add_data["short"] = text
            session.pending_add_step = "ask_doctor"
            await message.reply(
                "👨‍🏫 Almost done.\n\n"
                "Send the **Doctor's Name** (e.g., `Dr. Ahmed`),"
                " or type `skip` if you don't want to add one."
            )
            return

        if session.pending_add_step == "ask_doctor":
            doc = "" if text.lower() == "skip" else text
            session.pending_add_data["doctor"] = doc

            team = session.pending_add_team
            new_subject = SubjectConfig(
                name=session.pending_add_data["name"],
                short=session.pending_add_data["short"],
                doctor=doc,
                keywords=[team.display_name],
            )

            await message.reply(
                f"⏳ Saving `{new_subject.name}` to GitHub Secrets..."
            )

            scanner = ScannerService(discovery.graph, state)
            existing = scanner.load_subjects()
            existing.append(new_subject)
            json_str = json.dumps(
                {"subjects": [s.model_dump() for s in existing]}, indent=2
            )

            try:
                await rotate_github_secret("SUBJECTS_JSON", json_str)
                os.environ["SUBJECTS_JSON"] = json_str
                settings.subjects_json = json_str

                await message.reply(
                    f"✅ Success! **{new_subject.name}** is now"
                    " permanently configured and will be tracked automatically."
                )
            except Exception as e:
                await message.reply(
                    f"❌ Failed to save to GitHub Secrets: {e}\n\n"
                    "Make sure your GH_PAT is valid."
                )

            session.is_searching_teams = False
            session.pending_add_step = ""
            session.pending_add_team = None
            session.pending_add_data.clear()
            return

        await message.reply(f"🔍 Searching for '{text}'...")
        is_valid, msg, matched_teams = await discovery.search_teams(text)

        if not is_valid:
            await message.reply(msg)
            return

        if not matched_teams:
            await message.reply(
                msg + "\nTry a different keyword or `cancel`."
            )
            return

        session.pending_add_data["last_search_results"] = json.dumps(
            [t.model_dump() for t in matched_teams]
        )

        text, reply_markup = _build_search_page(matched_teams, 0)
        await message.reply(text, reply_markup=reply_markup)

    @app.on_callback_query(filters.regex(r"^srch_pg:") & owner_only)
    async def handle_search_page(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        
        results_str = session.pending_add_data.get("last_search_results")
        if not results_str:
            await cb.answer("Search results expired. Please search again.", show_alert=True)
            return
            
        page = int(cb.data.split(":")[1])
        teams_data = json.loads(results_str)
        matched_teams = [Team(**t) for t in teams_data]
        
        text, reply_markup = _build_search_page(matched_teams, page)
        
        await safe_edit_text(cb.message, text, reply_markup=reply_markup)
        await cb.answer()

    @app.on_callback_query(filters.regex(r"^del_subj:") & owner_only)
    async def handle_del_subj(client: Client, cb: CallbackQuery):
        idx = int(cb.data.split(":", 1)[1])

        scanner = ScannerService(discovery.graph, state)
        existing = scanner.load_subjects()

        if idx >= len(existing):
            await cb.answer(
                "Subject not found or already deleted.", show_alert=True
            )
            return

        subj_name = existing[idx].name
        existing.pop(idx)

        json_str = json.dumps(
            {"subjects": [s.model_dump() for s in existing]}, indent=2
        )

        await safe_edit_text(cb.message, 
            f"⏳ Deleting `{subj_name}` from GitHub Secrets..."
        )

        try:
            await rotate_github_secret("SUBJECTS_JSON", json_str)
            os.environ["SUBJECTS_JSON"] = json_str
            settings.subjects_json = json_str

            await safe_edit_text(cb.message, 
                f"✅ Success! **{subj_name}** has been permanently deleted."
            )
        except Exception as e:
            await safe_edit_text(cb.message, 
                f"❌ Failed to delete from GitHub Secrets: {e}"
            )

        await cb.answer()

    @app.on_callback_query(filters.regex(r"^add_team:") & owner_only)
    async def handle_add_team(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        team_id = cb.data.split(":", 1)[1]

        matched_teams_raw = session.pending_add_data.get(
            "last_search_results", "[]"
        )
        matched_teams = [
            Team(**t)
            for t in json.loads(matched_teams_raw)
        ]

        team = next(
            (t for t in matched_teams if t.id == team_id), None
        )
        if not team:
            await cb.answer("Team not found.", show_alert=True)
            return

        session.is_searching_teams = True
        session.pending_add_step = "ask_name"
        session.pending_add_team = team

        await safe_edit_text(cb.message, 
            f"📌 Adding: **{team.display_name}**\n\n"
            "Let's configure this subject.\n\n"
            "📝 **Step 1:** Send the **Full Name**\n"
            "   (e.g., `Database Systems`)\n\n"
            "_Type `cancel` to exit._"
        )
        await cb.answer()
