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

        buttons = [
            [
                InlineKeyboardButton(
                    f"➕ Add {t.display_name[:20]}...",
                    callback_data=f"add_team:{t.id}",
                )
            ]
            for t in matched_teams
        ]

        session.pending_add_data["last_search_results"] = json.dumps(
            [t.model_dump() for t in matched_teams]
        )

        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply(
            msg
            + "\n\n_Tap a team below to configure it,"
            " or type a new keyword to search again._",
            reply_markup=reply_markup,
        )

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

        await cb.message.edit_text(
            f"⏳ Deleting `{subj_name}` from GitHub Secrets..."
        )

        try:
            await rotate_github_secret("SUBJECTS_JSON", json_str)
            os.environ["SUBJECTS_JSON"] = json_str
            settings.subjects_json = json_str

            await cb.message.edit_text(
                f"✅ Success! **{subj_name}** has been permanently deleted."
            )
        except Exception as e:
            await cb.message.edit_text(
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

        await cb.message.edit_text(
            f"📌 Adding: **{team.display_name}**\n\n"
            "Let's configure this subject.\n\n"
            "📝 **Step 1:** Send the **Full Name**\n"
            "   (e.g., `Database Systems`)\n\n"
            "_Type `cancel` to exit._"
        )
        await cb.answer()
