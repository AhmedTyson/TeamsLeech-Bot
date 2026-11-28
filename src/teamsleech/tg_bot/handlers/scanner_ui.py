import calendar
import re
from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from teamsleech.services.scanner import ScannerService, subject_key
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_answer, safe_edit_text
from teamsleech.tg_bot.keyboards import (
    build_calendar_keyboard,
    build_checklist_keyboard,
)
from teamsleech.tg_bot.views import build_checklist_text, format_date_short, videos_first

MAX_DATE_RANGE_DAYS = 60

DATE_PROMPT = (
    "**Select Date Range** (default: everything)\n"
    "Tap a button, pick dates from the calendar, "
    "or type a date like `2026-04-01`.\n"
    "_Ranges up to 60 days. Type `cancel` to exit._"
)

def _build_date_choice_keyboard() -> InlineKeyboardMarkup:
    today = datetime.now(UTC).date()
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🗓 Last 60 Days", callback_data="date_btn:60d"
            ),
        ],
        [
            InlineKeyboardButton(
                "📆 Pick Dates",
                callback_data=f"cal:open:{today.year:04d}-{today.month:02d}",
            ),
        ],
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

def _render_calendar(
    year: int, month: int, subject: str | None, start: str | None
) -> tuple[str, InlineKeyboardMarkup]:
    if start:
        title = (
            f"📆 Start: **{format_date_short(start)}**"
            " — now pick the **end date**"
        )
    else:
        title = "📆 Pick the **start date**"
    title += f"\n_Subject: {subject or 'All Subjects'}_"
    return title, build_calendar_keyboard(year, month, picked_start=start)

def _get_current_week_range() -> tuple[str, str]:
    today = datetime.now(UTC).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()

def _looks_like_date_attempt(text: str) -> bool:
    """Heuristic: the user tried to type a date/range but it didn't parse.

    Used so a mistyped date always gets a helpful reply instead of silence,
    while ordinary chat text still propagates to other handlers.
    """
    if re.match(r"^\d{4}\s*[-/.]\s*\d{1,2}", text):
        return True
    if re.match(r"^\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{2,4}", text):
        return True
    return "إلى" in text or "الى" in text


DATE_HELP = (
    "❌ Could not understand that date. Try:\n"
    "• `2026-04-01`\n"
    "• `2026-04-01 to 2026-04-07`\n"
    "• `today`\n"
    "• `this week`\n"
    "• `march 2026`"
)


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
        r"^(\d{4}-\d{2}-\d{2})\s*(?:to|إلى|الى|–|—|-)\s*(\d{4}-\d{2}-\d{2})$",
        text, re.IGNORECASE,
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

async def run_missing_scan(client: Client, chat_id: int, scanner, state):
    """Scan every subject, queue only what the group hasn't seen yet.

    Already-published = the oldest (next_no - 1) recordings per subject
    (next_no is seeded/corrected with /setno). The rest is queued
    oldest-first into the normal review checklist.
    """
    from teamsleech.services.missing import unpublished_in_order

    await client.send_message(
        chat_id,
        "🗂 Scanning **all subjects** for unpublished recordings...",
    )
    try:
        results = await scanner.scan_recordings(None, None, None)
    except Exception as e:
        await client.send_message(chat_id, f"❌ Fetch error: {e}")
        return

    subjects_list = scanner.load_subjects()
    subj_map = {subject_key(s): s for s in subjects_list}

    filtered: dict[str, list] = {}
    skipped = 0
    for subj in subjects_list:
        key = subject_key(subj)
        recs = results.get(key, [])
        kept = unpublished_in_order(recs, subj.next_no)
        skipped += len(recs) - len(kept)
        if kept:
            filtered[key] = kept

    if not filtered:
        await client.send_message(
            chat_id,
            "✅ Nothing unpublished found "
            f"({skipped} already-published recording(s) skipped). "
            "If that looks wrong, fix numbering with /setno.",
        )
        return

    session = state.get_session(chat_id)
    for subj_name in filtered:
        filtered[subj_name] = videos_first(filtered[subj_name])
    session.pending_recordings = [r for recs in filtered.values() for r in recs]
    session.scan_label = "Unpublished (oldest first)"

    from teamsleech.services.triage import prepare_session

    prepare_session(session, subjects_list)

    text = build_checklist_text(
        filtered, session.scan_label, session.rename_overrides,
        subjects=subj_map, flags=session.triage_flags,
    )
    text += (
        f"\n\n_Skipped {skipped} already-published recording(s) by"
        " /setno numbering. Check the first item per subject before"
        " uploading._"
    )
    keyboard = build_checklist_keyboard(
        session.pending_recordings,
        session.selected_indices,
        session.rename_overrides,
    )
    await client.send_message(chat_id, text, reply_markup=keyboard)


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
            r for recs in results.values() for r in videos_first(recs)
        ]
        for subj_name in results:
            results[subj_name] = videos_first(results[subj_name])
        session.scan_label = label

        subj_map = {}
        subjects_list = scanner.load_subjects()
        for s in subjects_list:
            subj_map[subject_key(s)] = s

        from teamsleech.services.triage import prepare_session

        prepare_session(session, subjects_list)

        text = build_checklist_text(
            results, label, session.rename_overrides,
            subjects=subj_map, flags=session.triage_flags,
        )
        keyboard = (
            build_checklist_keyboard(
                session.pending_recordings,
                session.selected_indices,
                session.rename_overrides,
            )
            if session.pending_recordings
            else None
        )

        await client.send_message(chat_id, text, reply_markup=keyboard)

    @app.on_message(
        (filters.command("scanmissing") | filters.regex("^🗂 الناقص$") | filters.regex("^🗂 Scan Missing$"))
        & filters.private
        & owner_only
    )
    async def handle_scan_missing(client: Client, message: Message):
        await run_missing_scan(client, message.chat.id, scanner, state)

    @app.on_callback_query(filters.regex(r"^subj:") & owner_only)
    async def handle_subject_select(client: Client, cb: CallbackQuery):
        subject_key = cb.data.split(":", 1)[1]
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)

        if subject_key == "__ALL__":
            session.date_input_pending = True
            session.subject_filter = None
            prompt = "📚 **All subjects** selected.\n\n" + DATE_PROMPT
        else:
            session.date_input_pending = True
            session.subject_filter = subject_key
            prompt = f"📚 **{subject_key}** selected.\n\n" + DATE_PROMPT

        await safe_edit_text(
            cb.message,
            prompt,
            reply_markup=_build_date_choice_keyboard(),
        )
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
        session.cal_start = None
        
        await cb.answer("Starting scan...")

        if action == "60d":
            today = datetime.now(UTC).date()
            ds = (today - timedelta(days=60)).isoformat()
            de = today.isoformat()
            label = "Last 60 Days"
            await safe_edit_text(
                cb.message,
                f"🔍 Scanning **{session.subject_filter or 'All Subjects'}**"
                f" — {label}...",
            )
            await run_scan_and_reply(
                client, chat_id, session.subject_filter, ds, de, label
            )
            return

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

    @app.on_callback_query(filters.regex(r"^date:change") & owner_only)
    async def handle_date_change(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        session.date_input_pending = True

        await safe_edit_text(
            cb.message,
            "**Change Date Range** (default: everything)\n\n" + DATE_PROMPT,
            reply_markup=_build_date_choice_keyboard(),
        )
        await cb.answer()

    @app.on_callback_query(filters.regex(r"^cal:open:") & owner_only)
    async def handle_cal_open(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        session.cal_start = None
        year, month = (int(p) for p in cb.data.split(":")[2].split("-"))
        title, kb = _render_calendar(
            year, month, session.subject_filter, None
        )
        await safe_edit_text(cb.message, title, reply_markup=kb)
        await safe_answer(cb)

    @app.on_callback_query(filters.regex(r"^cal:nav:") & owner_only)
    async def handle_cal_nav(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        year, month = (int(p) for p in cb.data.split(":")[2].split("-"))
        title, kb = _render_calendar(
            year, month, session.subject_filter, session.cal_start
        )
        await safe_edit_text(cb.message, title, reply_markup=kb)
        await safe_answer(cb)

    @app.on_callback_query(filters.regex(r"^cal:day:") & owner_only)
    async def handle_cal_day(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        picked = cb.data.split(":", 2)[2]
        year, month = int(picked[:4]), int(picked[5:7])

        if not session.cal_start:
            session.cal_start = picked
            title, kb = _render_calendar(
                year, month, session.subject_filter, session.cal_start
            )
            await safe_edit_text(cb.message, title, reply_markup=kb)
            await safe_answer(cb, f"Start: {format_date_short(picked)}")
            return

        ds, de = session.cal_start, picked
        if de < ds:
            ds, de = de, ds

        ok, err = _validate_date_range(ds, de)
        if not ok:
            await cb.answer(err, show_alert=True)
            title, kb = _render_calendar(
                year, month, session.subject_filter, session.cal_start
            )
            await safe_edit_text(cb.message, title, reply_markup=kb)
            return

        session.cal_start = None
        session.date_input_pending = False
        label = f"{format_date_short(ds)} – {format_date_short(de)}"
        await safe_answer(cb, "Starting scan...")
        await safe_edit_text(
            cb.message,
            f"🔍 Scanning **{session.subject_filter or 'All Subjects'}**"
            f" — {label}...",
        )
        await run_scan_and_reply(
            client, chat_id, session.subject_filter, ds, de, label
        )

    @app.on_callback_query(filters.regex(r"^cal:cancel$") & owner_only)
    async def handle_cal_cancel(client: Client, cb: CallbackQuery):
        chat_id = cb.message.chat.id
        session = state.get_session(chat_id)
        session.cal_start = None
        session.date_input_pending = False
        session.subject_filter = None
        await safe_edit_text(cb.message, "❌ Date selection cancelled.")
        await safe_answer(cb)

    @app.on_callback_query(filters.regex(r"^cal:noop$") & owner_only)
    async def handle_cal_noop(client: Client, cb: CallbackQuery):
        await safe_answer(cb)

    @app.on_message(
        filters.text & filters.private & owner_only, group=2
    )
    async def handle_date_input(client: Client, message: Message):
        chat_id = message.chat.id
        session = state.get_session(chat_id)

        text = message.text.strip()

        if not session.date_input_pending:
            # Global fallback: a typed date works at any time, scoped to all
            # subjects, and always gets a reply (ack or clear error).
            parsed = _parse_date_input(text)
            if parsed is None:
                if _looks_like_date_attempt(text):
                    await message.reply(DATE_HELP)
                    return
                message.continue_propagation()
                return
            ds, de, label = parsed
            ok, err = _validate_date_range(ds, de or ds)
            if not ok:
                await message.reply(err)
                return
            await message.reply(
                f"🔍 Scanning **All Subjects** — {label}..."
            )
            await run_scan_and_reply(client, chat_id, None, ds, de, label)
            return

        if text.lower() == "cancel":
            session.date_input_pending = False
            session.cal_start = None
            session.subject_filter = None
            await message.reply("❌ Date selection cancelled.")
            return

        parsed = _parse_date_input(text)
        if parsed is None:
            await message.reply(DATE_HELP)
            return

        ds, de, label = parsed
        ok, err = _validate_date_range(ds, de or ds)
        if not ok:
            await message.reply(err)
            return

        session.date_input_pending = False

        await message.reply(
            f"🔍 Scanning **{session.subject_filter or 'All Subjects'}**"
            f" — {label}..."
        )
        await run_scan_and_reply(
            client, chat_id, session.subject_filter, ds, de, label
        )
