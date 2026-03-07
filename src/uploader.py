"""
Phase 4 — uploader

Streams selected .mp4 recordings from Microsoft Graph API to
Telegram Saved Messages via Pyrogram, with 10%-increment progress
messages (new messages, never edits existing ones).

Public API
----------
upload_recordings(recordings, access_token, tg_client, chat_id) → list[dict]
"""

import os
import logging
import tempfile
from typing import Any

import requests
from pyrogram import Client
from pyrogram.types import Message

log = logging.getLogger("uploader")

# ───────────────────────── constants ──────────────────────────

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB streaming chunks

# ───────────────────────── exceptions ────────────────────────────

class UploaderError(Exception):
    """Base exception for uploader failures."""

class DownloadError(UploaderError):
    """Raised when a Graph API download fails."""

class TelegramUploadError(UploaderError):
    """Raised when a Telegram upload fails."""

# ───────────────────────── download from Graph ────────────────

def _download_recording(
    drive_id: str,
    item_id: str,
    access_token: str,
    dest_path: str,
) -> int:
    """Stream-download a file from Graph API to a local temp path.

    Parameters
    ----------
    drive_id : str
        The SharePoint drive ID.
    item_id : str
        The SharePoint item ID.
    access_token : str
        Valid Graph API Bearer token.
    dest_path : str
        Local file path to write the downloaded bytes to.

    Returns
    -------
    int — total bytes written.
    """
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        resp = requests.get(
            url,
            headers=headers,
            allow_redirects=True,  # Graph returns 302 → CDN
            stream=True,
            timeout=60,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise DownloadError(f"Graph download failed: {exc}") from exc

    total_written = 0
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                f.write(chunk)
                total_written += len(chunk)

    log.info("Downloaded %d MB to %s", total_written // (1024 * 1024), dest_path)
    return total_written

# ───────────────────────── upload to Telegram ─────────────────

async def _upload_to_telegram(
    client: Client,
    chat_id: int,
    file_path: str,
    filename: str,
    file_size_bytes: int,
) -> Message:
    """Upload a file to Telegram Saved Messages with 10%-step progress.

    Sends a NEW message at every 10% milestone (never edits).
    Final message: ✅ [filename] — [size]MB — Saved to Telegram
    """
    milestones_sent: set[int] = set()
    last_progress_msg: Message | None = None

    # Pre-send a 0% message
    progress_text = f"📤 Uploading **{filename}**\n⏳ 0%"
    last_progress_msg = await client.send_message(chat_id, progress_text)

    async def progress_callback(current: int, total: int) -> None:
        nonlocal last_progress_msg
        if total == 0:
            return
        pct = int((current / total) * 100)
        # Round down to nearest 10
        milestone = (pct // 10) * 10
        if milestone > 0 and milestone not in milestones_sent:
            milestones_sent.add(milestone)
            bar_filled = milestone // 10
            bar_empty = 10 - bar_filled
            bar = "█" * bar_filled + "░" * bar_empty
            progress_text = (
                f"📤 **{filename}**\n"
                f"{bar} {milestone}%"
            )
            try:
                last_progress_msg = await client.send_message(
                    chat_id, progress_text
                )
            except Exception as e:
                log.warning("Progress message failed at %d%%: %s", milestone, e)

    try:
        sent_msg = await client.send_document(
            chat_id=chat_id,
            document=file_path,
            file_name=filename,
            caption=f"🎥 {filename}",
            progress=progress_callback,
        )
    except Exception as exc:
        raise TelegramUploadError(
            f"Telegram upload failed for {filename}: {exc}"
        ) from exc

    # Final confirmation message
    size_mb = round(file_size_bytes / (1024 * 1024), 1)
    await client.send_message(
        chat_id,
        f"✅ **{filename}** — {size_mb}MB — Saved to Telegram"
    )

    log.info("Uploaded %s to Telegram (chat_id=%d)", filename, chat_id)
    return sent_msg

# ───────────────────────── main entry point ───────────────────

async def upload_recordings(
    recordings: list[dict],
    access_token: str,
    tg_client: Client,
    chat_id: int,
) -> list[dict]:
    """Download recordings from Graph and upload to Telegram.

    Parameters
    ----------
    recordings : list[dict]
        List of recording dicts from fetcher, each with:
        name, size_mb, created, drive_id, item_id, team_name
    access_token : str
        Valid Graph API Bearer token.
    tg_client : Client
        An already-started Pyrogram client.
    chat_id : int
        Telegram chat ID for Saved Messages.

    Returns
    -------
    list[dict] — results per recording:
        - name: str
        - success: bool
        - error: str | None
    """
    results: list[dict] = []

    for rec in recordings:
        filename = rec["name"]
        drive_id = rec["drive_id"]
        item_id = rec["item_id"]

        log.info("Processing: %s (drive=%s, item=%s)", filename, drive_id, item_id)

        # Use a temp file for the download
        tmp_dir = tempfile.mkdtemp(prefix="teamsleech_")
        tmp_path = os.path.join(tmp_dir, filename)

        try:
            # Step 1: Download from Graph API
            await tg_client.send_message(
                chat_id,
                f"⬇️ Downloading **{filename}** from Teams..."
            )
            file_size = _download_recording(
                drive_id, item_id, access_token, tmp_path
            )

            # Step 2: Upload to Telegram
            await _upload_to_telegram(
                tg_client, chat_id, tmp_path, filename, file_size
            )

            results.append({
                "name": filename,
                "success": True,
                "error": None,
            })

        except (DownloadError, TelegramUploadError) as exc:
            log.error("Failed: %s — %s", filename, exc)
            try:
                await tg_client.send_message(
                    chat_id,
                    f"❌ Failed: **{filename}**\n{exc}"
                )
            except Exception:
                pass
            results.append({
                "name": filename,
                "success": False,
                "error": str(exc),
            })

        except Exception as exc:
            log.error("Unexpected error for %s: %s", filename, exc)
            results.append({
                "name": filename,
                "success": False,
                "error": str(exc),
            })

        finally:
            # Clean up temp file
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                os.rmdir(tmp_dir)
            except OSError:
                pass

    # Summary
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    summary = f"📊 **Upload complete:** {success_count} succeeded"
    if fail_count:
        summary += f", {fail_count} failed"
    await tg_client.send_message(chat_id, summary)

    return results
