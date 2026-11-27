"""Remember failed downloads per chat and retry them.

Failures are recorded as they happen (upload checklist) so a successful
Microsoft login — or a tap on the 🔁 Retry failed button — re-runs them
without making the user rescan and reselect.
"""

import logging

from pyrogram import Client
from pyrogram.types import Message

from teamsleech.models.domain import Recording
from teamsleech.services.state import StateManager
from teamsleech.services.transfer import TransferService

log = logging.getLogger("retry_failed")


def _rec_key(rec: Recording) -> tuple[str, str]:
    return (rec.drive_id, rec.item_id)


def record_failed(state: StateManager, chat_id: int, rec: Recording) -> None:
    """Remember a failed download once (deduped by drive/item).

    Stored on the StateManager, not the per-scan session, so rescans do
    not wipe the retry queue.
    """
    state.add_failed_download(chat_id, rec)


async def retry_failed_downloads(
    client: Client,
    message: Message,
    transfer: TransferService,
    state: StateManager,
) -> int:
    """Re-run the recorded failed downloads. Returns the success count."""
    from teamsleech.tg_bot.handlers.upload_ui import _failure_keyboard

    chat_id = message.chat.id
    recs = state.get_failed_downloads(chat_id)
    if not recs:
        await message.reply("✅ Nothing waiting to retry.")
        return 0

    await message.reply(f"🔁 Retrying {len(recs)} failed download(s)…")

    succeeded: list[Recording] = []
    failed_again: list[Recording] = []

    async def progress_cb(action: str, data: dict) -> None:
        idx = data.get("index", 0)
        rec = recs[idx] if 0 <= idx < len(recs) else None
        if action == "file_done" and rec is not None:
            succeeded.append(rec)
        elif action == "error":
            if rec is not None and all(
                id(x) != id(rec) for x in failed_again
            ):
                failed_again.append(rec)
            err = data.get("error", "unknown")
            await message.reply(
                f"❌ `{data.get('name', 'file')}` failed again:\n{err}",
                reply_markup=_failure_keyboard(err),
            )

    try:
        results = await transfer.upload_recordings(recs, progress_cb)
    except Exception as exc:
        log.warning("Retry run errored: %s", exc)
        await message.reply(f"❌ Retry run failed: {exc}")
        return 0

    for r in results or []:
        rec = r.get("rec")
        if rec is None:
            continue
        if r.get("success"):
            if all(id(x) != id(rec) for x in succeeded):
                succeeded.append(rec)
        elif all(id(x) != id(rec) for x in failed_again):
            failed_again.append(rec)

    ok_keys = {_rec_key(r) for r in succeeded}
    newly_recorded = [
        f
        for f in state.get_failed_downloads(chat_id)
        if all(_rec_key(f) != _rec_key(r) for r in recs)
    ]
    remaining = [
        f for f in failed_again if _rec_key(f) not in ok_keys
    ] + newly_recorded
    state.set_failed_downloads(chat_id, remaining)

    if succeeded and not remaining:
        await message.reply(
            f"✅ Retry complete — {len(succeeded)} file(s) uploaded."
        )
    elif succeeded:
        await message.reply(
            f"✅ {len(succeeded)} uploaded,"
            f" ❌ {len(remaining)} still failing"
            " — tap 🔑 Login and retry again."
        )
    else:
        await message.reply(
            "❌ Still failing — tap 🔑 Login to refresh the Microsoft"
            " session, then retry."
        )
    return len(succeeded)
