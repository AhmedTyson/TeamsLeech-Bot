import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from teamsleech.core.config import settings
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

log = logging.getLogger("commands")


def register_commands(
    app: Client,
    scanner: ScannerService,
    state: StateManager,
    discovery: DiscoveryService,
    transfer=None,
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
            "• Tap a subject → pick scope (60 days default)\n"
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
            "Scope defaults to the last 60 days.\n"
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

    async def _do_login(client: Client, message: Message):
        await message.reply(
            "🔑 Starting Microsoft login — the next message has your link."
        )
        from teamsleech.services.reauth import run_reauth_flow

        ok = await run_reauth_flow(client, settings.telegram_chat_id)
        if not ok:
            return
        # Refresh the live Graph token so this run uses the new session too.
        try:
            from teamsleech.services.auth import authenticate

            discovery.graph.access_token = await authenticate()
            await message.reply(
                "✅ Session active. Downloads now use your Microsoft session"
                " — no cookie exports needed."
            )
        except Exception as e:
            await message.reply(
                f"⚠️ Logged in and saved, but refreshing this run failed: {e}"
            )

        # Auto-retry downloads that failed before the login.
        failed = state.get_failed_downloads(settings.telegram_chat_id)
        if transfer is not None and failed:
            try:
                from teamsleech.tg_bot.retry_failed import (
                    retry_failed_downloads,
                )

                await message.reply(
                    f"🔁 Retrying {len(failed)} failed"
                    " download(s) with the new session…"
                )
                await retry_failed_downloads(client, message, transfer, state)
            except Exception as e:
                log.warning("Auto-retry after login failed: %s", e)

    @app.on_message(filters.command("login") & filters.private & owner_only)
    async def handle_login(client: Client, message: Message):
        await _do_login(client, message)

    @app.on_message(
        filters.regex("^🔑 Microsoft Login$") & filters.private & owner_only
    )
    async def handle_login_button(client: Client, message: Message):
        await _do_login(client, message)

    @app.on_callback_query(filters.regex(r"^login:start$") & owner_only)
    async def handle_login_cb(client: Client, cb):
        from teamsleech.tg_bot.handlers import safe_answer

        await safe_answer(cb, "Starting login...")
        await _do_login(client, cb.message)

    async def _do_browser_login(client: Client, message: Message):
        """Dispatch the remote-browser self-login run (browser-login.yml).

        The owner logs into the real Microsoft page himself inside a remote
        browser; the run saves the SharePoint cookies. Nothing he types
        reaches the bot.
        """
        from teamsleech.services.github_actions import dispatch_workflow

        try:
            await dispatch_workflow("browser-login.yml")
        except Exception as e:
            await message.reply(f"❌ Could not start the browser login run: `{e}`")
            return
        await message.reply(
            "🖥 **Browser login starting** — your private link arrives in"
            " about a minute.\n\n"
            "You log into Microsoft's real page yourself; nothing you type"
            " reaches the bot. Once the SharePoint site loads, the session"
            " is saved automatically and a fresh check run starts."
        )

    @app.on_message(filters.command("browserlogin") & filters.private & owner_only)
    async def handle_browser_login(client: Client, message: Message):
        await _do_browser_login(client, message)

    @app.on_message(
        filters.regex("^🖥 Browser Login$") & filters.private & owner_only
    )
    async def handle_browser_login_button(client: Client, message: Message):
        await _do_browser_login(client, message)

    @app.on_message(filters.command("topics") & filters.private & owner_only)
    async def handle_topics(client: Client, message: Message):
        subjects = scanner.load_subjects()
        if not subjects:
            await message.reply("No subjects configured yet.")
            return
        lines = ["🗂 **Topic links & numbering**\n"]
        for s in subjects:
            topic = f"`{s.topic_id}`" if s.topic_id else "❌ not linked"
            prefix = "Sec" if s.kind == "section" else "L"
            lines.append(
                f"📚 **{s.name}** (`{s.short or s.name}`)\n"
                f"   topic: {topic}  |  type: {s.kind}  |  next: {prefix}{s.next_no:02d}"
            )
        lines.append(
            "\n**Link a topic:** inside the group, open the topic and send"
            " `/link <SHORT>` (e.g. `/link FT`).\n"
            "**Fix numbering:** send `/setno <SHORT> <N>` here."
        )
        await message.reply("\n".join(lines))

    @app.on_message(filters.command("setno") & filters.private & owner_only)
    async def handle_setno(client: Client, message: Message):
        parts = message.text.split()
        if len(parts) != 3 or not parts[2].isdigit():
            await message.reply("Usage: `/setno <SHORT> <N>` — e.g. `/setno FT 8`")
            return
        short, n = parts[1].strip().lower(), int(parts[2])
        subjects = scanner.load_subjects()
        subj = next(
            (s for s in subjects if (s.short or s.name).strip().lower() == short),
            None,
        )
        if not subj:
            await message.reply(f"❌ No subject with short code `{parts[1]}`.")
            return
        subj.next_no = n
        try:
            from teamsleech.services.subjects_store import persist_subjects

            await persist_subjects(subjects)
        except Exception as e:
            await message.reply(f"❌ Failed to save: {e}")
            return
        prefix = "Sec" if subj.kind == "section" else "L"
        await message.reply(f"✅ **{subj.name}** will continue from {prefix}{n:02d}.")

    @app.on_message(filters.command("link") & filters.group)
    async def handle_link_topic(client: Client, message: Message):
        # Only the owner may link topics, and only inside a forum topic.
        sender = getattr(message, "from_user", None)
        if not sender or sender.id != settings.telegram_chat_id:
            return
        thread_id = getattr(message, "message_thread_id", None)
        if not thread_id:
            await message.reply("⚠️ Send /link inside a forum topic.")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.reply("Usage: `/link <SHORT>` — e.g. `/link FT`")
            return
        short = parts[1].strip().lower()
        subjects = scanner.load_subjects()
        subj = next(
            (s for s in subjects if (s.short or s.name).strip().lower() == short),
            None,
        )
        if not subj:
            await message.reply(f"❌ No subject with short code `{parts[1]}`.")
            return
        subj.topic_id = thread_id
        try:
            from teamsleech.services.subjects_store import persist_subjects

            await persist_subjects(subjects)
        except Exception as e:
            await message.reply(f"❌ Linked, but saving failed: {e}")
            return

        note = ""
        if settings.target_chat_id() is None:
            try:
                await persist_target_chat_id(message.chat.id)
                note = "\n📤 Group saved for publishing — no extra secret needed."
            except Exception as e:
                note = (
                    "\n⚠️ Could not save the group id for publishing"
                    f" automatically: {e}"
                )
        await message.reply(f"✅ **{subj.name}** linked to this topic.{note}")

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


async def persist_target_chat_id(chat_id: int) -> None:
    """Store the forum group id as TELEGRAM_TARGET_CHAT_ID (secret + memory).

    Lets the first /link inside the group double as publishing setup, so the
    owner never creates that secret by hand.
    """
    from teamsleech.services.github_secrets import rotate_github_secret

    gid = str(chat_id)
    await rotate_github_secret("TELEGRAM_TARGET_CHAT_ID", gid)
    settings.telegram_target_chat_id = gid
