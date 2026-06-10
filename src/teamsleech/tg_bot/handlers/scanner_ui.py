import calendar
from datetime import UTC, date as date_type, datetime, timedelta
import re

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_edit_text
from teamsleech.tg_bot.keyboards import build_checklist_keyboard
from teamsleech.tg_bot.views import build_checklist_text, format_date_short

MAX_DATE_RANGE_DAYS = 30

def _get_current_week_range() -> tuple[str, str]:
    today = datetime.now(UTC).date()
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
        today_str = datetime.now(UTC).date().isoformat()
        return today_str, None, f"Today ({format_date_short(today_str)})"

    if text == "this week":
        mon, sun = _get_current_week_range()
        return (
            mon,
            sun,
            f"This Week ({format_date_short(mon)} – {format_date_short(sun)})",
        )

    range_match = re.match(
        r"^(\d{4}-\d{2}-\d{2})\s*(?:to|-)\s*(\d{4}-\d{2}-\d{2})$", text, re.IGNORECASE
    )
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
        "january": 1, "february": 2, "march": 3, "april": 4,
        "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }
    month_match = re.match(r"^([a-z]+)(?:\s+(\d{4}))?$", text)
    if month_match:
        m_name, year_str = month_match.groups()
        if m_name in month_map:
            m_num = month_map[m_name]
            year = int(year_str) if year_str else datetime.now().year
            _, last_day = calendar.monthrange(year, m_num)
            ds = f"{year}-{m_num:02d}-01"
            de = f"{year}-{m_num:02d}-{last_day:02d}"
            return ds, de, f"{m_name.capitalize()} {year}"

    return None

def register_scanner_ui(app: Client, scanner: ScannerService, state: StateManager):
    async def run_scan_and_reply(
        client: Client,
        chat_id: int,
        subject_filter: str | None,
        date_start: str | None,
        date_end: str | None,
        label: str,
    ):
        try:
            results = await scanner.scan_recordings(
                subject_filter, date_start, date_end
            )
        except Exception as e:
            await client.send_message(chat_id, f"❌ Fetch error: {e}")
            return

        session = state.get_session(chat_id)
        session.pending_recordings = [
            r for recs in results.values() for r in recs
        ]
        session.selected_indices.clear()
        session.rename_overrides.clear()
        session.scan_label = label

        text = build_checklist_text(results, label)
        keyboard = (
            build_checklist_keyboard(
                session.pending_recordings, session.selected_indices
            )
            if session.pending_recordings
            else None
        )

        await client.send_message(chat_id, text, reply_markup=keyboard)

    @app.on_callback_query(filters.regex(r"^subj:") & owner_only)
    async def handle_subject_select(client: Client, cb: CallbackQuery):
        subject_key = cb.data.split(":", 1)[1]
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)

        if subject_key == "__ALL__":
            label = "Since Last Run"
            await safe_edit_text(
                cb.message,
                f"🔍 Scanning **all subjects** — {label}...",
            )
            await run_scan_and_reply(
                client, chat_id, None, None, None, label
            )
            await cb.answer()
        else:
            session.date_input_pending = True
            session.subject_filter = subject_key

            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📅 Today", callback_data="date_btn:today"
                    ),
                    InlineKeyboardButton(
                        "📅 This Week", callback_data="date_btn:this week"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "♾️ All Time", callback_data="date_btn:all"
                    ),
                ],
            ])

            prompt = (
                f"📚 **{subject_key}** selected.\n\n"
                "**Select Date Range**\n"
                "Tap a button below, or type a custom date like `2026-04-01`.\n"
                "_Type `cancel` to exit._"
            )
            await safe_edit_text(cb.message, prompt, reply_markup=kb)
            await cb.answer()

    @app.on_callback_query(filters.regex(r"^date_btn:") & owner_only)
    async def handle_date_btn(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)

        if not session.date_input_pending:
            await cb.answer("Date selection expired.", show_alert=True)
            return

        action = cb.data.split(":", 1)[1]
        session.date_input_pending = False

        if action == "all":
            label = "All Time"
            await safe_edit_text(
                cb.message,
                f"🔍 Scanning **{session.subject_filter or 'All Subjects'}**"
                f" — {label}...",
            )
            await run_scan_and_reply(
                client, chat_id, session.subject_filter, None, None, label
            )
            await cb.answer()
            return

        parsed = _parse_date_input(action)
        if parsed:
            ds, de, label = parsed
            await safe_edit_text(
                cb.message,
                f"🔍 Scanning **{session.subject_filter or 'All Subjects'}**"
                f" — {label}...",
            )
            await run_scan_and_reply(
                client, chat_id, session.subject_filter, ds, de, label
            )

        await cb.answer()

    @app.on_callback_query(filters.regex(r"^date:change") & owner_only)
    async def handle_date_change(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        session.date_input_pending = True

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📅 Today", callback_data="date_btn:today"
                ),
                InlineKeyboardButton(
                    "📅 This Week", callback_data="date_btn:this week"
                ),
            ],
            [
                InlineKeyboardButton(
                    "♾️ All Time", callback_data="date_btn:all"
                ),
            ],
        ])

        await safe_edit_text(
            cb.message,
            "**Change Date Range**\n\n"
            "Tap a button below, or type a custom date like `2026-04-01`.\n"
            "_Type `cancel` to exit._",
            reply_markup=kb,
        )
        await cb.answer()

    @app.on_message(
        filters.text & filters.private & owner_only, group=2
    )
    async def handle_date_input(client: Client, message: Message):
        chat_id = message.chat.id
        session = state.get_session(chat_id)

        if not session.date_input_pending:
            message.continue_propagation()
            return

        text = message.text.strip()

        if text.lower() == "cancel":
            session.date_input_pending = False
            session.subject_filter = None
            await message.reply("❌ Date selection cancelled.")
            return

        parsed = _parse_date_input(text)
        if parsed is None:
            await message.reply(
                "❌ Could not understand that date. Try:\n"
                "• `2026-04-01`\n"
                "• `2026-04-01 to 2026-04-07`\n"
                "• `today`\n"
                "• `this week`\n"
                "• `march 2026`"
            )
            return

        session.date_input_pending = False
        ds, de, label = parsed

        await message.reply(
            f"🔍 Scanning **{session.subject_filter or 'All Subjects'}**"
            f" — {label}..."
        )
        await run_scan_and_reply(
            client, chat_id, session.subject_filter, ds, de, label
        )
