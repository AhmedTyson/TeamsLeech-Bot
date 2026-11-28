from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from teamsleech.models.domain import Recording, SubjectConfig

REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🗂 الناقص"), KeyboardButton("⚙️ الإعداد")],
        [KeyboardButton("🔍 فحص بتاريخ"), KeyboardButton("📊 الحالة")],
        [KeyboardButton("🖥 تسجيل الدخول"), KeyboardButton("🛑 إيقاف")],
    ],
    resize_keyboard=True,
)

def build_subject_keyboard(subjects: list[SubjectConfig]) -> InlineKeyboardMarkup:
    buttons = []
    row = []

    for subj in subjects:
        row.append(
            InlineKeyboardButton(
                text=subj.short or subj.name, callback_data=f"subj:{subj.name}"
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            text="✅ Check All", callback_data="subj:__ALL__"
        )
    ])
    return InlineKeyboardMarkup(buttons)

MAX_TOGGLE_ITEMS = 45
TOGGLES_PER_ROW = 4

def _build_toggle_rows(flat: list[Recording], selections: set[int]) -> list[list[InlineKeyboardButton]]:
    buttons: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for i in range(min(len(flat), MAX_TOGGLE_ITEMS)):
        mark = "✅" if i in selections else "⬛️"
        current_row.append(
            InlineKeyboardButton(text=f"{mark} {i + 1}", callback_data=f"sel:{i}")
        )
        current_row.append(
            InlineKeyboardButton(text="✏️", callback_data=f"ren:{i}")
        )
        if len(current_row) >= TOGGLES_PER_ROW:
            buttons.append(current_row)
            current_row = []
    if current_row:
        buttons.append(current_row)
    return buttons

def _build_upload_button(flat: list[Recording], selections: set[int]) -> list[InlineKeyboardButton]:
    if not selections:
        label = "📤 Upload (Select items first)"
    else:
        total_mb = sum(flat[i].size_mb for i in selections if i < len(flat))
        label = f"🚀 Upload Selected ({len(selections)} files, {total_mb:.0f} MB)"
    return [InlineKeyboardButton(text=label, callback_data="upload:confirm")]

def _build_filter_row(flat: list[Recording], selections: set[int]) -> list[InlineKeyboardButton]:
    n_video = sum(1 for r in flat if r.is_video)
    n_doc = len(flat) - n_video
    row: list[InlineKeyboardButton] = []
    if n_doc > 0:
        n_sel = sum(1 for i in selections if i < len(flat) and not flat[i].is_video)
        row.append(InlineKeyboardButton(text=f"📄 PDFs {n_sel}/{n_doc}", callback_data="sel:pdfs"))
    if n_video > 0:
        n_sel = sum(1 for i in selections if i < len(flat) and flat[i].is_video)
        row.append(InlineKeyboardButton(text=f"🎬 Videos {n_sel}/{n_video}", callback_data="sel:videos"))
    all_selected = len(selections) == len(flat) and len(flat) > 0
    label = "➖ All" if all_selected else "➕ All"
    row.append(InlineKeyboardButton(text=label, callback_data="sel:all"))
    return row

def _build_action_row(flat: list[Recording]) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if flat:
        row.append(
            InlineKeyboardButton(
                text="✅ Approve all & Upload",
                callback_data="upload:all",
            )
        )
    row.append(
        InlineKeyboardButton(text="📅 Change Date", callback_data="date:change")
    )
    row.append(InlineKeyboardButton(text="❌ Cancel", callback_data="cancel:check"))
    return row

def build_checklist_keyboard(
    flat: list[Recording],
    selections: set[int],
    rename_overrides: dict[int, str] | None = None,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    buttons.extend(_build_toggle_rows(flat, selections))
    buttons.append(_build_upload_button(flat, selections))
    buttons.append(_build_filter_row(flat, selections))
    buttons.append(_build_action_row(flat))
    return InlineKeyboardMarkup(buttons)


def build_manage_dashboard(
    subjects: list[SubjectConfig],
) -> tuple[str, InlineKeyboardMarkup]:
    lines = [f"⚙️ **Subjects ({len(subjects)})** — tap a number:"]
    for i, s in enumerate(subjects):
        doc = f" — {s.doctor}" if s.doctor else " — (no doctor)"
        lines.append(f"{i + 1}. **{s.name}**{doc}")
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i in range(len(subjects)):
        row.append(
            InlineKeyboardButton(text=f"[ {i + 1} ]", callback_data=f"mng:sel:{i}")
        )
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="➕ Add New", callback_data="mng:add"),
        InlineKeyboardButton(text="📤 Show JSON", callback_data="mng:show"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def build_manage_detail(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(text="✏️ Edit", callback_data=f"mng:edit:{idx}"),
            InlineKeyboardButton(text="❌ Delete", callback_data=f"mng:del:{idx}"),
        ],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="mng:list")],
    ])


MANAGE_FIELDS: list[tuple[str, str]] = [
    ("name", "Name"),
    ("short", "Short"),
    ("doctor", "Doctor"),
    ("subj_kw", "Subject keys"),
    ("doc_kw", "Doctor keys"),
    ("kind", "Type (lecture/section)"),
]


def build_manage_fields(idx: int) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for n, (key, label) in enumerate(MANAGE_FIELDS):
        row.append(
            InlineKeyboardButton(
                text=f"{n + 1} {label}", callback_data=f"mng:field:{idx}:{key}"
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="⬅️ Back", callback_data=f"mng:sel:{idx}")
    ])
    return InlineKeyboardMarkup(buttons)

WEEKDAY_HEADER = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

def build_calendar_keyboard(
    year: int, month: int, picked_start: str | None = None
) -> InlineKeyboardMarkup:
    """Month-grid calendar for picking a date range. Day cells carry
    `cal:day:YYYY-MM-DD`; navigation carries `cal:nav:YYYY-MM`; the picked
    start date (ISO) is highlighted with dots."""
    import calendar as _cal

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    rows: list[list[InlineKeyboardButton]] = []
    rows.append([
        InlineKeyboardButton("◀", callback_data=f"cal:nav:{prev_year:04d}-{prev_month:02d}"),
        InlineKeyboardButton(f"{_cal.month_name[month]} {year}", callback_data="cal:noop"),
        InlineKeyboardButton("▶", callback_data=f"cal:nav:{next_year:04d}-{next_month:02d}"),
    ])
    rows.append([
        InlineKeyboardButton(d, callback_data="cal:noop") for d in WEEKDAY_HEADER
    ])

    for week in _cal.monthcalendar(year, month):
        row: list[InlineKeyboardButton] = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal:noop"))
            else:
                iso = f"{year:04d}-{month:02d}-{day:02d}"
                label = f"•{day}•" if iso == picked_start else str(day)
                row.append(InlineKeyboardButton(label, callback_data=f"cal:day:{iso}"))
        rows.append(row)

    rows.append([
        InlineKeyboardButton("✖ Cancel", callback_data="cal:cancel"),
    ])
    return InlineKeyboardMarkup(rows)
