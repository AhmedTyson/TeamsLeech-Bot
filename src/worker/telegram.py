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
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=30.0,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    result = data.get("result", {})
    return result.get("message_id") if isinstance(result, dict) else None


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
    if session:
        client = Client(
            "worker_user", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True
        )
    elif bot_token:
        size = await asyncio.to_thread(os.path.getsize, path)
        if size > 50 * 1024 * 1024:
            print(f"upload skipped: {path} exceeds 50 MB bot cap, no user session")
            return None
        client = Client(
            "worker_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token, in_memory=True
        )
    else:
        print("upload skipped: no session string or bot token")
        return None
    await client.start()
    try:
        msg = await client.send_document(int(chat_id), path, caption=caption[:1024])
        return msg.id if msg is not None else None
    finally:
        await client.stop()
