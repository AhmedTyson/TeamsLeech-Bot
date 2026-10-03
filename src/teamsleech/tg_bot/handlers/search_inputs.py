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
from teamsleech.services.discovery import DiscoveryService
from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_answer, safe_edit_text
from teamsleech.tg_bot.keyboards import (
    MANAGE_FIELDS,
    build_manage_dashboard,
    build_manage_detail,
    build_manage_fields,
)


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
        return (
            session.is_searching_teams
            or session.pending_add_step != ""
            or session.pending_edit_idx is not None
        )

    search_filter = filters.create(is_searching)

    async def _persist_subjects(existing) -> str:
        from teamsleech.services.subjects_store import save_subjects_text_async
        json_str = json.dumps(
            {"subjects": [s.model_dump() for s in existing]}, indent=2
        )
        source = await save_subjects_text_async(json_str)
        if source == "secret":
            os.environ["SUBJECTS_JSON"] = json_str
            settings.subjects_json = json_str
        return source

    def _detail_text(s) -> str:
        return (
            f"📚 **{s.name}**\n"
            f"   🏷 Short: `{s.short or '—'}`\n"
            f"   👨‍🏫 Doctor: `{s.doctor or '—'}`\n"
            f"   🔎 Subject keys: `{', '.join(s.keywords) or '—'}`\n"
            f"   🩺 Doctor keys: `{', '.join(s.doctor_keywords) or '—'}`"
        )

    def _load_existing() -> list:
        scanner = ScannerService(discovery.graph, state)
        return scanner.load_subjects()

    async def _apply_edit(client: Client, message: Message, session) -> None:
        idx = session.pending_edit_idx or 0
        field = session.pending_edit_field
        text = message.text.strip()
        existing = _load_existing()
        if idx >= len(existing):
            session.pending_edit_idx = None
            session.pending_edit_field = ""
            await message.reply(
                "Subject list changed — reopen 📚 Subjects."
            )
            return
        if text.lower() not in ("keep", "skip"):
            subj = existing[idx]
            if field in ("subj_kw", "doc_kw"):
                vals = (
                    []
                    if text.lower() == "clear"
                    else [k.strip() for k in text.split(",") if k.strip()]
                )
                if field == "subj_kw":
                    subj.keywords = vals
                else:
                    subj.doctor_keywords = vals
                if not subj.keywords and not subj.doctor_keywords:
                    await message.reply(
                        "❌ At least one keyword list must stay non-empty."
                        " Send new keywords, `clear` is not allowed for both."
                    )
                    return
                from teamsleech.services.scanner import validate_keyword_lists
                kw_errors = validate_keyword_lists(
                    subj.keywords, subj.doctor_keywords
                )
                if kw_errors:
                    await message.reply(
                        "❌ Keywords rejected:\n- "
                        + "\n- ".join(kw_errors)
                        + "\n\nSend new keywords, or `keep`."
                    )
                    return
            elif field == "name":
                subj.name = text
            elif field == "short":
                subj.short = text
            elif field == "doctor":
                subj.doctor = "" if text.lower() == "clear" else text
            try:
                await _persist_subjects(existing)
            except Exception as e:
                await message.reply(f"❌ Failed to save: {e}")
                return
            await message.reply(f"✅ Updated **{subj.name}**.")
        session.pending_edit_idx = None
        session.pending_edit_field = ""
        shown = _load_existing()
        if idx < len(shown):
            await message.reply(
                _detail_text(shown[idx]),
                reply_markup=build_manage_detail(idx),
            )
        else:
            text, markup = build_manage_dashboard(shown)
            await message.reply(text, reply_markup=markup)

    async def _finish_add(message: Message, session) -> None:
        new_subject = SubjectConfig(
            name=session.pending_add_data["name"],
            short=session.pending_add_data["short"],
            doctor=session.pending_add_data.get("doctor", ""),
            keywords=session.pending_add_data.get("subj_kw", []),
            doctor_keywords=session.pending_add_data.get("doc_kw", []),
        )

        await message.reply(
            f"⏳ Saving `{new_subject.name}`..."
        )

        scanner = ScannerService(discovery.graph, state)
        existing = scanner.load_subjects()
        existing.append(new_subject)

        try:
            source = await _persist_subjects(existing)

            rule_parts = []
            if new_subject.keywords:
                rule_parts.append(f"subject [{', '.join(new_subject.keywords)}]")
            if new_subject.doctor_keywords:
                rule_parts.append(
                    f"doctor [{', '.join(new_subject.doctor_keywords)}]"
                )
            await message.reply(
                f"✅ Success! **{new_subject.name}** is now"
                f" permanently configured (saved to {source}) and will be"
                " tracked automatically.\n"
                f"Matches {' + '.join(rule_parts)}."
            )
        except Exception as e:
            await message.reply(
                f"❌ Failed to save: {e}\n\n"
                "Make sure your GH_PAT is valid (and has 'gist' scope"
                " when using a gist)."
            )

        session.is_searching_teams = False
        session.pending_add_step = ""
        session.pending_add_team = None
        session.pending_add_data.clear()

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
            session.pending_edit_idx = None
            session.pending_edit_field = ""
            await message.reply("❌ Subject setup cancelled.")
            return

        if session.pending_edit_idx is not None:
            await _apply_edit(client, message, session)
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
            session.pending_add_step = "ask_subj_kw"
            team = session.pending_add_team
            team_name = team.display_name if team else "this team"
            await message.reply(
                "🔎 Step 3: Send **SUBJECT keywords** (e.g., `Data Security`),\n"
                f"`same` to use `{team_name}`, or `skip`."
            )
            return

        if session.pending_add_step == "ask_subj_kw":
            team = session.pending_add_team
            fallback = [team.display_name] if team else []
            if text.lower() == "skip":
                subj_kw = []
            elif text.lower() == "same":
                subj_kw = fallback
            else:
                subj_kw = [k.strip() for k in text.split(",") if k.strip()]
            session.pending_add_data["subj_kw"] = subj_kw
            session.pending_add_step = "ask_doc_kw"
            await message.reply(
                "👨‍🏫 Step 4: Send **DOCTOR keywords** (e.g., `Hany`),\n"
                "or type `skip`.\n"
                "_At least one of Steps 3–4 is required._"
            )
            return

        if session.pending_add_step == "ask_doc_kw":
            doc_kw = (
                []
                if text.lower() == "skip"
                else [k.strip() for k in text.split(",") if k.strip()]
            )
            subj_kw = session.pending_add_data.get("subj_kw", [])
            if not subj_kw and not doc_kw:
                await message.reply(
                    "❌ Give at least a subject or a doctor keyword.\n\n"
                    "Send subject keywords, or type `cancel` to exit."
                )
                session.pending_add_step = "ask_subj_kw"
                return
            session.pending_add_data["doc_kw"] = doc_kw
            from teamsleech.services.scanner import validate_keyword_lists
            kw_errors = validate_keyword_lists(subj_kw, doc_kw)
            if kw_errors:
                await message.reply(
                    "❌ Keywords rejected:\n- "
                    + "\n- ".join(kw_errors)
                    + "\n\nSend subject keywords again, or `cancel`."
                )
                session.pending_add_step = "ask_subj_kw"
                return
            team = session.pending_add_team
            if team is not None:
                tmp = SubjectConfig(
                    name="tmp", keywords=subj_kw, doctor_keywords=doc_kw
                )
                checker = ScannerService(discovery.graph, state)
                if not checker._match_teams([team], tmp):
                    await message.reply(
                        f"⚠️ These keywords don't match **{team.display_name}**"
                        " itself — the subject would grab nothing.\n\n"
                        "Send subject keywords again, or `cancel`."
                    )
                    session.pending_add_step = "ask_subj_kw"
                    return
            if doc_kw:
                session.pending_add_step = "ask_doc_label"
                await message.reply(
                    "🏷 Display name for the doctor? Send it, `same` to use"
                    " your keywords, or `skip` for none."
                )
            else:
                session.pending_add_data["doctor"] = ""
                await _finish_add(message, session)
            return

        if session.pending_add_step == "ask_doc_label":
            lowered = text.lower()
            if lowered == "skip":
                doc = ""
            elif lowered == "same":
                doc = ", ".join(session.pending_add_data.get("doc_kw", []))
            else:
                doc = text
            session.pending_add_data["doctor"] = doc
            await _finish_add(message, session)
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

        await safe_edit_text(cb.message,
            f"⏳ Deleting `{subj_name}`..."
        )

        try:
            await _persist_subjects(existing)

            await safe_edit_text(cb.message,
                f"✅ Success! **{subj_name}** has been permanently deleted."
            )
        except Exception as e:
            await safe_edit_text(cb.message,
                f"❌ Failed to delete: {e}"
            )

        await safe_answer(cb)

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

    @app.on_callback_query(filters.regex(r"^mng:") & owner_only)
    async def handle_manage(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        parts = cb.data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "list":
            text, markup = build_manage_dashboard(_load_existing())
            await safe_edit_text(cb.message, text, reply_markup=markup)
            await cb.answer()
            return

        if action == "add":
            session.is_searching_teams = True
            await safe_edit_text(
                cb.message,
                "🔍 **Add New Subject**\n\n"
                "Send a keyword (at least 3 characters) to search"
                " your joined Teams.\n_Type `cancel` to exit._",
            )
            await cb.answer()
            return

        if action == "show":
            from io import BytesIO
            existing = _load_existing()
            payload = json.dumps(
                {"subjects": [s.model_dump() for s in existing]}, indent=2
            ).encode("utf-8")
            bio = BytesIO(payload)
            bio.name = "subjects.json"
            await cb.message.reply_document(
                bio,
                file_name="subjects.json",
                caption="📤 Current subjects config — paste into your gist.",
            )
            await safe_answer(cb)
            return

        try:
            idx = int(parts[2]) if len(parts) > 2 else -1
        except ValueError:
            await cb.answer("Invalid selection.", show_alert=True)
            return
        existing = _load_existing()
        if idx < 0 or idx >= len(existing):
            await cb.answer(
                "Subject list changed — reopen 📚 Subjects.", show_alert=True
            )
            return
        subj = existing[idx]

        if action == "sel":
            await safe_edit_text(
                cb.message, _detail_text(subj),
                reply_markup=build_manage_detail(idx),
            )
            await cb.answer()
        elif action == "edit":
            await safe_edit_text(
                cb.message,
                f"What to edit for **{subj.name}**?",
                reply_markup=build_manage_fields(idx),
            )
            await cb.answer()
        elif action == "field":
            field = parts[3] if len(parts) > 3 else ""
            labels = dict(MANAGE_FIELDS)
            if field not in labels:
                await cb.answer("Invalid field.", show_alert=True)
                return
            session.pending_edit_idx = idx
            session.pending_edit_field = field
            if field == "subj_kw":
                current = ", ".join(subj.keywords)
            elif field == "doc_kw":
                current = ", ".join(subj.doctor_keywords)
            elif field == "name":
                current = subj.name
            elif field == "short":
                current = subj.short
            else:
                current = subj.doctor
            extra = (
                " (comma-separated; `clear` empties, `keep` cancels)"
                if field in ("subj_kw", "doc_kw") else " (`keep` cancels)"
            )
            await safe_edit_text(
                cb.message,
                f"✏️ Send new **{labels[field]}** (current: `{current or '—'}`){extra}.",
            )
            await cb.answer()
        elif action == "del":
            await safe_edit_text(
                cb.message,
                f"Delete **{subj.name}**? This removes it from tracking.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "Yes, delete", callback_data=f"mng:del_yes:{idx}"
                        ),
                        InlineKeyboardButton(
                            "Keep", callback_data=f"mng:sel:{idx}"
                        ),
                    ]
                ]),
            )
            await cb.answer()
        elif action == "del_yes":
            name = subj.name
            existing.pop(idx)
            await safe_answer(cb, "Deleting...")
            try:
                await _persist_subjects(existing)
            except Exception as e:
                await safe_edit_text(cb.message, f"❌ Failed to delete: {e}")
                return
            text, markup = build_manage_dashboard(existing)
            await safe_edit_text(
                cb.message, f"✅ Deleted **{name}**.\n\n{text}",
                reply_markup=markup,
            )
            await safe_answer(cb)
        else:
            await safe_answer(cb)
