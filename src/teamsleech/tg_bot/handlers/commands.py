from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.keyboards import REPLY_KEYBOARD, build_subject_keyboard
from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.services.discovery import DiscoveryService

def register_commands(app: Client, scanner: ScannerService, state: StateManager, discovery: DiscoveryService):
    
    @app.on_message(filters.command("start") & filters.private & owner_only)
    async def handle_start(client: Client, message: Message):
        await message.reply(
            "🎓 **𝗧𝗲𝗮𝗺𝘀𝗟𝗲𝗲𝗰𝗵 𝗕𝗼𝘁**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗖𝗼𝗺𝗺𝗮𝗻𝗱𝘀:**\n"
            "🔍 `/check`   — Scan for new files & recordings\n"
            "📚 `/subjects` — Manage your courses\n\n"
            "💡 **𝗤𝘂𝗶𝗰𝗸 𝗔𝗰𝗰𝗲𝘀𝘀:**\n"
            "• Tap a subject → scans **this week** automatically\n"
            "• Send a date: `2026-04-01`\n"
            "• Send a range: `2026-04-01 to 2026-04-07`\n"
            "• Type `today` or `this week`\n\n"
            "_Tap_ 🔍 **Check Recordings** _below to get started!_",
            reply_markup=REPLY_KEYBOARD,
        )

    @app.on_message((filters.command("check") | filters.regex("^🔍 Check Recordings$")) & filters.private & owner_only)
    async def handle_check(client: Client, message: Message):
        subjects = scanner.load_subjects()
        keyboard = build_subject_keyboard(subjects)
        await message.reply(
            "**What do you want to check?**\n\n"
            "💡 _Tip: Send a date like_ `2026-04-01` _or range like_\n"
            "`2026-04-01 to 2026-04-07` _to check specific dates._",
            reply_markup=keyboard,
        )

    @app.on_message((filters.command("subjects") | filters.regex("^📚 Subjects$")) & filters.private & owner_only)
    async def handle_subjects(client: Client, message: Message):
        session = state.get_session(message.chat.id)
        session.is_searching_teams = True
        
        subjects = scanner.load_subjects()
        msg_text = "⚙️ **𝗖𝗼𝘂𝗿𝘀𝗲 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁 𝗗𝗮𝘀𝗵𝗯𝗼𝗮𝗿𝗱**\n━━━━━━━━━━━━━━━━━━━━━━\nHere are the subjects you are currently tracking:\n\n"
        
        buttons = []
        for i, s in enumerate(subjects):
            doc = s.doctor or "None"
            msg_text += f"📚 **{s.name}**\n   🏷 Short: `{s.short}`\n   👨‍🏫 Doctor: `{doc}`\n\n"
            
            btn_text = f"❌ Delete {s.short or s.name}"
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"del_subj:{i}")])
            
        msg_text += "┄" * 20 + "\n\n"
        msg_text += "🔍 **𝗔𝗱𝗱 𝗡𝗲𝘄 𝗖𝗼𝘂𝗿𝘀𝗲**\n"
        msg_text += "Send a keyword (at least 3 characters) to search your joined Teams.\n"
        msg_text += "_Type `cancel` at any time to exit._"
        
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        
        await message.reply(msg_text, reply_markup=reply_markup)

