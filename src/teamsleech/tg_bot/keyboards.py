from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from teamsleech.models.domain import Recording, SubjectConfig

REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔍 Check Recordings"), KeyboardButton("📚 Subjects")],
        [KeyboardButton("⚙️ Background Runner")],
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
            text="✅ Check All (since last run)", callback_data="subj:__ALL__"
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

def _build_action_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text="📅 Change Date", callback_data="date:change"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel:check"),
    ]

def build_checklist_keyboard(
    flat: list[Recording],
    selections: set[int],
    rename_overrides: dict[int, str] | None = None,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    buttons.extend(_build_toggle_rows(flat, selections))
    buttons.append(_build_upload_button(flat, selections))
    buttons.append(_build_filter_row(flat, selections))
    buttons.append(_build_action_row())
    return InlineKeyboardMarkup(buttons)


def build_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Start Runner", callback_data="act:run")],
        [InlineKeyboardButton("🔄 Check Status", callback_data="act:status")],
        [InlineKeyboardButton("🛑 Cancel Active Runs", callback_data="act:cancel")]
    ])

