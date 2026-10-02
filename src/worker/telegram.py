"""Telegram delivery: Bot API notify + MTProto upload. No Graph."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx


def notify(text: str) -> int | None:
    """Send a Bot API message. Returns message_id or None when unconfigured."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("notify skipped: bot token/chat missing")
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = httpx.post(
        url,
        json={"chat_id": chat_id, "text": text},
        timeout=30.0,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    result = data.get("result", {})
    return result.get("message_id") if isinstance(result, dict) else None


async def _start_client(client: object) -> None:
    """Start with one FloodWait backoff; re-raise with a hint if still limited."""
    from pyrogram.errors import FloodWait

    try:
        await client.start()  # type: ignore[attr-defined]
    except FloodWait as exc:
        wait = min(int(getattr(exc, "value", 0) or 0), 1500)
        print(f"Telegram flood wait: sleeping {wait}s before one retry.")
        await asyncio.sleep(wait)
    else:
        return
    try:
        await client.start()  # type: ignore[attr-defined]
    except FloodWait as exc:
        msg = (
            "Telegram still rate-limiting logins. Mint TELEGRAM_SESSION_STRING "
            f"(user session avoids bot-login floods) and re-run. Detail: {exc}"
        )
        raise RuntimeError(msg) from exc


async def upload_file(path: str, caption: str) -> int | None:
    """Upload via user session (large) or bot (<=50 MB). Returns message id."""
    from pyrogram.client import Client

    api_id = int(os.environ.get("TELEGRAM_API_ID", "0") or 0)
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    session = os.environ.get("TELEGRAM_SESSION_STRING", "")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not api_id or not api_hash or not chat_id:
        print("upload skipped: Telegram API config missing")
        return None
    session_dir = os.environ.get("TG_SESSION_DIR", ".tg-sessions")
    os.makedirs(session_dir, exist_ok=True)
    if session:
        client = Client(
            "worker_user",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session,
            workdir=session_dir,
        )
    elif bot_token:
        size = await asyncio.to_thread(os.path.getsize, path)
        if size > 50 * 1024 * 1024:
            print(f"upload skipped: {path} exceeds 50 MB bot cap, no user session")
            return None
        client = Client(
            "worker_bot",
            api_id=api_id,
            api_hash=api_hash,
            bot_token=bot_token,
            workdir=session_dir,
        )
    else:
        print("upload skipped: no session string or bot token")
        return None
    await _start_client(client)
    try:
        msg = await client.send_document(int(chat_id), path, caption=caption[:1024])
        return msg.id if msg is not None else None
    finally:
        await client.stop()
