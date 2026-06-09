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

def build_checklist_keyboard(
    flat: list[Recording],
    selections: set[int],
    rename_overrides: dict[int, str] | None = None,
) -> InlineKeyboardMarkup:
    buttons = []
    current_row = []

    for i in range(min(len(flat), 45)):
        mark = "✅" if i in selections else "⬛️"
        current_row.append(
            InlineKeyboardButton(text=f"{mark} {i + 1}", callback_data=f"sel:{i}")
        )
        current_row.append(
            InlineKeyboardButton(text="✏️", callback_data=f"ren:{i}")
        )

        if len(current_row) >= 4:
            buttons.append(current_row)
            current_row = []

    if current_row:
        buttons.append(current_row)

    if not selections:
        upload_label = "📤 Upload (Select items first)"
    else:
        total_mb = sum(flat[i].size_mb for i in selections if i < len(flat))
        upload_label = (
            f"🚀 Upload Selected ({len(selections)} files, {total_mb:.0f} MB)"
        )

    buttons.append([
        InlineKeyboardButton(text=upload_label, callback_data="upload:confirm")
    ])

    all_selected = len(selections) == len(flat) and len(flat) > 0
    select_label = "➖ Deselect All" if all_selected else "➕ Select All"

    buttons.append([
        InlineKeyboardButton(text=select_label, callback_data="sel:all"),
        InlineKeyboardButton(text="📅 Change Date", callback_data="date:change"),
    ])

    buttons.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel:check"),
    ])

    return InlineKeyboardMarkup(buttons)
