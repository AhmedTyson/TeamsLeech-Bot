from pyrogram import Client, filters
from pyrogram.types import Message

from tg_bot.filters import owner_only
from tg_bot.keyboards import REPLY_KEYBOARD, build_subject_keyboard
from services.scanner import ScannerService
from services.state import StateManager
from services.discovery import DiscoveryService

def register_commands(app: Client, scanner: ScannerService, state: StateManager, discovery: DiscoveryService):
    
    @app.on_message(filters.command("start") & filters.private & owner_only)
    async def handle_start(client: Client, message: Message):
        await message.reply(
            "📡 **TeamsLeech Bot**\n\n"
            "Available commands:\n"
            "/check   — 🔍 Scan for new lecture recordings\n"
            "/subjects — 📚 Manage your courses\n\n"
            "💡 **Quick access:**\n"
            "• Tap a subject → scans **this week** automatically\n"
            "• Send a date: `2026-04-01`\n"
            "• Send a range: `2026-04-01 to 2026-04-07`\n"
            "• Type `today` or `this week`\n\n"
            "Tap /check to get started.",
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
        msg_text = "📚 **Current Subjects Configured:**\n"
        for s in subjects:
            doc = s.doctor or "No doctor set"
            msg_text += f"• **{s.name}** (Short: `{s.short}`, Doc: `{doc}`)\n"
            
        msg_text += "\n🔍 **Find New Courses**\n"
        msg_text += "Send a keyword (at least 3 characters) to search your joined Teams.\n"
        msg_text += "_Type `cancel` to exit search mode._"
        
        await message.reply(msg_text)
