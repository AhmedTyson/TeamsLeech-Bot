import re
from datetime import datetime, timezone, date as date_type, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from tg_bot.filters import owner_only
from tg_bot.views import build_checklist_text, format_date_short
from tg_bot.keyboards import build_checklist_keyboard
from services.scanner import ScannerService
from services.state import StateManager

MAX_DATE_RANGE_DAYS = 30

def _get_current_week_range() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()

def _validate_date_range(start: str, end: str) -> tuple[bool, str]:
    try:
        s = date_type.fromisoformat(start)
        e = date_type.fromisoformat(end)
    except ValueError:
        return False, "❌ Invalid date format. Use `YYYY-MM-DD`."
    if s > e:
        return False, "❌ Start date must be before or equal to end date."
    if (e - s).days > MAX_DATE_RANGE_DAYS:
        return False, f"❌ Date range cannot exceed {MAX_DATE_RANGE_DAYS} days."
    return True, ""

def _parse_date_input(text: str) -> tuple[str, str | None, str] | None:
    text = text.strip().lower()

    if text == "today":
        today_str = datetime.now(timezone.utc).date().isoformat()
        return today_str, None, f"Today ({format_date_short(today_str)})"

    if text == "this week":
        mon, sun = _get_current_week_range()
        return mon, sun, f"This Week ({format_date_short(mon)} – {format_date_short(sun)})"

    range_match = re.match(r"^(\d{4}-\d{2}-\d{2})\s*(?:to|-)\s*(\d{4}-\d{2}-\d{2})$", text, re.IGNORECASE)
    if range_match:
        ds, de = range_match.group(1), range_match.group(2)
        return ds, de, f"{format_date_short(ds)} – {format_date_short(de)}"

    date_match = re.match(r"^(\d{4}-\d{2}-\d{2})$", text)
    if date_match:
        ds = date_match.group(1)
        return ds, None, format_date_short(ds)

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }
    month_match = re.match(r"^([a-z]+)(?:\s+(\d{4}))?$", text)
    if month_match:
        m_name, year_str = month_match.groups()
        if m_name in month_map:
            import calendar
            m_num = month_map[m_name]
            year = int(year_str) if year_str else datetime.now().year
            _, last_day = calendar.monthrange(year, m_num)
            ds = f"{year}-{m_num:02d}-01"
            de = f"{year}-{m_num:02d}-{last_day:02d}"
            return ds, de, f"{m_name.capitalize()} {year}"

    return None

def register_scanner_ui(app: Client, scanner: ScannerService, state: StateManager):

    async def run_scan_and_reply(client: Client, chat_id: int, subject_filter: str | None, date_start: str | None, date_end: str | None, label: str):
        try:
            results = await scanner.scan_recordings(subject_filter, date_start, date_end)
        except Exception as e:
            await client.send_message(chat_id, f"❌ Fetch error: {e}")
            return

        session = state.get_session(chat_id)
        session.pending_recordings = [r for recs in results.values() for r in recs]
        session.selected_indices.clear()
        session.rename_overrides.clear()
        session.scan_label = label
        
        text = build_checklist_text(results, label)
        keyboard = build_checklist_keyboard(session.pending_recordings, session.selected_indices) if session.pending_recordings else None
        
        await client.send_message(chat_id, text, reply_markup=keyboard)

    @app.on_callback_query(filters.regex(r"^subj:") & owner_only)
    async def handle_subject_select(client: Client, cb: CallbackQuery):
        subject_key = cb.data.split(":", 1)[1]
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)

        if subject_key == "__ALL__":
            label = "Since Last Run"
            await cb.message.edit_text(f"🔍 Scanning **all subjects** — {label}...")
            await run_scan_and_reply(client, chat_id, None, None, None, label)
            await cb.answer()
        else:
            session.date_input_pending = True
            session.subject_filter = subject_key
            prompt = (
                f"📚 **{subject_key}** selected.\n\n"
                "📅 **Select Date Range**\n"
                "Send one of:\n"
                "• `2026-04-01` — single date\n"
                "• `2026-04-01 to 2026-04-07` — date range\n"
                "• `today` — today only\n"
                "• `this week` — current week\n\n"
                "_Type your choice below:_"
            )
            await cb.message.edit_text(prompt)
            await cb.answer()

    @app.on_message(filters.text & filters.private & owner_only)
    async def handle_date_input(client: Client, message: Message):
        chat_id = message.chat.id
        session = state.get_session(chat_id)
        
        # Don't hijack if searching or renaming
        if session.is_searching_teams or session.pending_rename_idx is not None:
            message.continue_propagation()
            
        text = message.text.strip()
        parsed = _parse_date_input(text)
        
        if session.date_input_pending:
            if text.lower() == "cancel":
                session.date_input_pending = False
                await message.reply("❌ Date selection cancelled.")
                return
                
            if not parsed:
                await message.reply("❌ Couldn't parse that date.\nType `cancel` to exit.")
                return
                
            session.date_input_pending = False
            ds, de, label = parsed
            
            if de:
                valid, err = _validate_date_range(ds, de)
                if not valid:
                    await message.reply(err)
                    return
                    
            subj_label = session.subject_filter or "All Subjects"
            await message.reply(f"🔍 Scanning **{subj_label}** — {label}...")
            await run_scan_and_reply(client, chat_id, session.subject_filter, ds, de, label)
            return

        # Direct global shortcuts
        if parsed:
            ds, de, label = parsed
            if de:
                valid, err = _validate_date_range(ds, de)
                if not valid:
                    await message.reply(err)
                    return
            await message.reply(f"🔍 Scanning **all subjects** — {label}...")
            await run_scan_and_reply(client, chat_id, None, ds, de, label)
            return
            
        # Try direct subject match
        subjects = scanner.load_subjects()
        matched = None
        for s in subjects:
            if text.lower() in [s.name.lower(), s.short.lower()] + [k.lower() for k in s.keywords]:
                matched = s.name
                break
                
        if matched:
            session.date_input_pending = True
            session.subject_filter = matched
            await message.reply(f"📚 **{matched}** selected.\n\n📅 **Select Date Range** (e.g., `today`, `this week`)")
            return
            
        message.continue_propagation()
