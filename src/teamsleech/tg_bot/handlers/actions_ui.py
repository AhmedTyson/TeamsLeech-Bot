from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from teamsleech.services.github_actions import cancel_run, get_active_runs, trigger_workflow
from teamsleech.tg_bot.filters import owner_only
from teamsleech.tg_bot.handlers import safe_edit_text
from teamsleech.tg_bot.keyboards import build_actions_keyboard


def register_actions_ui(app: Client) -> None:
    @app.on_message(
        (filters.command("runner") | filters.regex("^⚙️ Background Runner$"))
        & filters.private
        & owner_only
    )
    async def handle_runner_cmd(client: Client, message: Message):
        text = (
            "⚙️ **GitHub Actions Control Panel**\n\n"
            "Manage the background bot runner seamlessly without visiting GitHub."
        )
        await message.reply(text, reply_markup=build_actions_keyboard())

    @app.on_callback_query(filters.regex(r"^act:(run|status|cancel)$") & owner_only)
    async def handle_action_btn(client: Client, cb: CallbackQuery):
        action = cb.data.split(":")[1]
        
        try:
            if action == "run":
                await cb.answer("Triggering workflow...")
                await trigger_workflow()
                await safe_edit_text(
                    cb.message, 
                    "✅ **Workflow triggered successfully!**\n\n"
                    "The runner should start shortly. Use 'Check Status' to monitor it.",
                    reply_markup=build_actions_keyboard()
                )
                
            elif action == "status":
                await cb.answer("Checking status...")
                runs = await get_active_runs()
                if not runs:
                    msg = "💤 **No active runs.** The runner is idle."
                else:
                    lines = ["🔄 **Active Runs:**\n"]
                    for r in runs:
                        status_emoji = "⏳" if r['status'] == "queued" else "🔄"
                        lines.append(f"{status_emoji} `{r['name']}` (ID: `{r['id']}`) - {r['status']}")
                    msg = "\n".join(lines)
                    
                await safe_edit_text(
                    cb.message, 
                    msg,
                    reply_markup=build_actions_keyboard()
                )
                
            elif action == "cancel":
                await cb.answer("Fetching active runs to cancel...")
                runs = await get_active_runs()
                if not runs:
                    await safe_edit_text(
                        cb.message, 
                        "💤 **No active runs to cancel.**",
                        reply_markup=build_actions_keyboard()
                    )
                    return
                    
                await safe_edit_text(
                    cb.message, 
                    f"🛑 Cancelling {len(runs)} active run(s)...",
                )
                
                for r in runs:
                    await cancel_run(r["id"])
                    
                await safe_edit_text(
                    cb.message, 
                    f"✅ **Successfully cancelled {len(runs)} run(s).**",
                    reply_markup=build_actions_keyboard()
                )
        except Exception as e:
            await safe_edit_text(
                cb.message, 
                f"❌ **Error communicating with GitHub:**\n`{str(e)}`",
                reply_markup=build_actions_keyboard()
            )
