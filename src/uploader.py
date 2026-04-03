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
import subprocess
import json as _json
from typing import Any

import requests
from pyrogram import Client
from pyrogram.errors import BadRequest
from pyrogram.types import Message

log = logging.getLogger("uploader")

# ───────────────────────── constants ──────────────────────────────

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB streaming chunks

# ───────────────────────── exceptions ─────────────────────────────

class UploaderError(Exception):
    """Base exception for uploader failures."""

class DownloadError(UploaderError):
    """Raised when a Graph API download fails."""

class TelegramUploadError(UploaderError):
    """Raised when a Telegram upload fails."""

# ───────────────────────── video metadata ─────────────────────────

def _probe_video(file_path: str) -> tuple[int, int, int]:
    """Extract duration (seconds), width, height using ffprobe.

    Returns (duration_s, width, height).
    Falls back to (0, 1280, 720) on any error so upload never fails.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-show_format",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = _json.loads(result.stdout)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                w = int(stream.get("width", 1280))
                h = int(stream.get("height", 720))
                dur = stream.get("duration")
                if dur is None:
                    # Some containers store duration on the format level
                    fmt = data.get("format", {})
                    dur = fmt.get("duration", 0)
                return int(float(dur)), w, h
    except Exception as exc:
        log.warning("ffprobe failed for %s: %s — using defaults", file_path, exc)
    return 0, 1280, 720

# ───────────────────────── download from Graph ────────────────────

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

# ───────────────────────── upload to Telegram ─────────────────────

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
    all_progress_msgs: list[Message] = []

    # Pre-send a 0% message
    progress_text = f"📤 Uploading **{filename}**\n⏳ 0%"
    initial_msg = await client.send_message(chat_id, progress_text)
    all_progress_msgs.append(initial_msg)

    async def progress_callback(current: int, total: int) -> None:
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
                msg = await client.send_message(
                    chat_id, progress_text
                )
                all_progress_msgs.append(msg)
            except Exception as e:
                log.warning("Progress message failed at %d%%: %s", milestone, e)

    # Extract video metadata for proper Telegram rendering
    duration, width, height = _probe_video(file_path)

    try:
        # Issue 1: send_video for inline playback
        sent_msg = await client.send_video(
            chat_id=chat_id,
            video=file_path,
            file_name=filename,
            caption=f"🎥 {filename}",
            supports_streaming=True,
            duration=duration,
            width=width,
            height=height,
            progress=progress_callback,
        )
    except BadRequest:
        # Issue 2: codec incompatibility fallback → send as document
        log.warning(
            "send_video rejected for %s — falling back to send_document",
            filename,
        )
        try:
            sent_msg = await client.send_document(
                chat_id=chat_id,
                document=file_path,
                file_name=filename,
                caption=(
                    f"🎥 {filename}\n"
                    "(⚠️ inline play unavailable — tap to download)"
                ),
                progress=progress_callback,
            )
        except Exception as exc:
            raise TelegramUploadError(
                f"Telegram fallback upload failed for {filename}: {exc}"
            ) from exc
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

    # Delete all progress messages on success
    for msg in all_progress_msgs:
        try:
            await msg.delete()
        except Exception as e:
            log.warning("Failed to delete progress message: %s", e)

    log.info("Uploaded %s to Telegram (chat_id=%d)", filename, chat_id)
    return sent_msg

# ───────────────────────── main entry point ───────────────────────

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
    # Issue 4: strip whitespace from access_token to prevent corruption
    access_token = access_token.strip()

    results: list[dict] = []

    try:
        for rec in recordings:
            filename = rec["name"]
            drive_id = rec["drive_id"]
            item_id = rec["item_id"]

            log.info("Processing: %s (drive=%s, item=%s)", filename, drive_id, item_id)

            # Use a named temp file for the download (no directory to clean)
            tmp_file = tempfile.NamedTemporaryFile(
                suffix=".mp4", prefix="teamsleech_", delete=False
            )
            tmp_path = tmp_file.name
            tmp_file.close()  # close handle so _download_recording can write

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
                # Issue 3: alert on unhandled exception
                try:
                    await tg_client.send_message(
                        chat_id,
                        f"❌ Upload failed: **{filename}**\n"
                        f"Error: {type(exc).__name__}: {exc}\n"
                        f"Phase: uploader.py"
                    )
                except Exception:
                    pass
                results.append({
                    "name": filename,
                    "success": False,
                    "error": str(exc),
                })
                raise  # re-raise so main.py knows

            finally:
                # Clean up temp file — always runs
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    except (DownloadError, TelegramUploadError, UploaderError):
        pass  # already handled and appended to results above

    # Summary
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    summary = f"📊 **Upload complete:** {success_count} succeeded"
    if fail_count:
        summary += f", {fail_count} failed"
    await tg_client.send_message(chat_id, summary)

    return results
