from pyrogram import Client, filters
from pyrogram.types import Message

from teamsleech.services.discovery import DiscoveryService
from teamsleech.services.github_actions import cancel_run, get_active_runs
from teamsleech.services.scanner import ScannerService
from teamsleech.services.state import StateManager
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_edit_text
from teamsleech.tg_bot.keyboards import (
    REPLY_KEYBOARD,
    build_manage_dashboard,
    build_subject_keyboard,
)


def register_commands(
    app: Client, scanner: ScannerService, state: StateManager, discovery: DiscoveryService
):
    @app.on_message(filters.command("start") & filters.private & owner_only)
    async def handle_start(client: Client, message: Message):
        await message.reply(
            "🎓 **𝗧𝗲𝗮𝗺𝘀𝗟𝗲𝗲𝗰𝗵 𝗕𝗼𝘁**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗖𝗼𝗺𝗺𝗮𝗻𝗱𝘀:**\n"
            "🔍 `/check`   — Scan for new files & recordings\n"
            "📚 `/subjects` — Manage your courses\n"
            "⚙️ `/runner`   — Manage background workflow\n\n"
            "💡 **𝗤𝘂𝗶𝗰𝗸 𝗔𝗰𝗰𝗲𝘀𝘀:**\n"
            "• Tap a subject → scans **this week** automatically\n"
            "• Send a date: `2026-04-01`\n"
            "• Send a range: `2026-04-01 to 2026-04-07`\n"
            "• Type `today` or `this week`\n\n"
            "_Tap_ 🔍 **Check Recordings** _below to get started!_",
            reply_markup=REPLY_KEYBOARD,
        )

    @app.on_message(
        (filters.command("check") | filters.regex("^🔍 Check Recordings$"))
        & filters.private
        & owner_only
    )
    async def handle_check(client: Client, message: Message):
        subjects = scanner.load_subjects()
        keyboard = build_subject_keyboard(subjects)
        await message.reply(
            "**What do you want to check?**\n\n"
            "💡 _Tip: Send a date like_ `2026-04-01` _or range like_\n"
            "`2026-04-01 to 2026-04-07` _to check specific dates._",
            reply_markup=keyboard,
        )

    @app.on_message(
        (filters.command("subjects") | filters.regex("^📚 Subjects$"))
        & filters.private
        & owner_only
    )
    async def handle_subjects(client: Client, message: Message):
        subjects = scanner.load_subjects()
        text, reply_markup = build_manage_dashboard(subjects)
        await message.reply(text, reply_markup=reply_markup)

    @app.on_message(
        (filters.command("runner") | filters.regex("^⚙️ Background Runner$"))
        & filters.private
        & owner_only
    )
    async def handle_runner_removed(client: Client, message: Message):
        await message.reply(
            "⚙️ Runner panel removed. Runs start on schedule or manual dispatch"
            " in GitHub. To stop one, use 🛑 Cancel Workflow."
        )

    @app.on_message(
        filters.regex("^🛑 Cancel Workflow$")
        & filters.private
        & owner_only
    )
    async def handle_cancel_workflow(client: Client, message: Message):
        notice = await message.reply("🛑 Checking active runs...")
        try:
            runs = await get_active_runs()
        except Exception as e:
            await safe_edit_text(notice, f"❌ GitHub unreachable: {e}")
            return
        if not runs:
            await safe_edit_text(notice, "💤 Runner idle — nothing to cancel.")
            return
        try:
            for r in runs:
                await cancel_run(r["id"])
        except Exception as e:
            await safe_edit_text(notice, f"❌ GitHub unreachable: {e}")
            return
        await safe_edit_text(
            notice, f"✅ Cancelled {len(runs)} run(s)."
        )
