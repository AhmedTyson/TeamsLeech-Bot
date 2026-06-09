from typing import List, Set, Dict, Optional
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from teamsleech.models.domain import SubjectConfig, Recording

# Persistent reply keyboard shown at the bottom of every message
REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔍 Check Recordings"), KeyboardButton("📚 Subjects")],
    ],
    resize_keyboard=True,
)

def build_subject_keyboard(subjects: List[SubjectConfig]) -> InlineKeyboardMarkup:
    """Build the /check subject selection keyboard."""
    buttons = []
    row = []

    for subj in subjects:
        row.append(InlineKeyboardButton(text=subj.short or subj.name, callback_data=f"subj:{subj.name}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
            
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="✅ Check All (since last run)", callback_data="subj:__ALL__")])
    return InlineKeyboardMarkup(buttons)

def build_checklist_keyboard(
    flat: List[Recording],
    selections: Set[int],
    rename_overrides: Optional[Dict[int, str]] = None,
) -> InlineKeyboardMarkup:
    """Build the checkbox + rename + upload + select-all keyboard."""
    buttons = []
    current_row = []
    
    for i, rec in enumerate(flat):
        if i >= 45: # Telegram strict hard limit of 100 inline buttons per message
            break

        mark = "✅" if i in selections else "⬛️"
        current_row.append(InlineKeyboardButton(text=f"{mark} {i + 1}", callback_data=f"sel:{i}"))
        current_row.append(InlineKeyboardButton(text="✏️", callback_data=f"ren:{i}"))
        
        if len(current_row) >= 4:
            buttons.append(current_row)
            current_row = []
            
    if current_row:
        buttons.append(current_row)

    if not selections:
        upload_label = "📤 Upload (Select items first)"
    else:
        total_mb = sum(flat[i].size_mb for i in selections if i < len(flat))
        upload_label = f"🚀 Upload Selected ({len(selections)} files, {total_mb:.0f} MB)"

    buttons.append([InlineKeyboardButton(text=upload_label, callback_data="upload:confirm")])

    all_selected = len(selections) == len(flat) and len(flat) > 0
    select_label = "➖ Deselect All" if all_selected else "➕ Select All"
    
    buttons.append([
        InlineKeyboardButton(text=select_label, callback_data="sel:all"),
        InlineKeyboardButton(text="📅 Change Date", callback_data="date:change")
    ])

    buttons.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel:check"),
    ])

    return InlineKeyboardMarkup(buttons)
