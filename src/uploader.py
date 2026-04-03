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
import asyncio
import logging
import tempfile
import subprocess
import json as _json
import re
from typing import Any, Callable

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

def _extract_thumbnail(video_path: str) -> str | None:
    """Extract a thumbnail from the video using ffmpeg at 00:00:02."""
    thumb_path = video_path + ".jpg"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-ss", "00:00:02",
                "-vframes", "1",
                "-q:v", "2",
                thumb_path
            ],
            capture_output=True,
            timeout=20,
            check=True
        )
        if os.path.exists(thumb_path):
            return thumb_path
    except Exception as exc:
        log.warning("Thumbnail extraction failed: %s", exc)
    return None

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
    tg_progress_cb: Callable | None = None,
) -> Message:
    """Upload a file to Telegram Saved Messages."""
    # Extract video metadata and thumbnail
    duration, width, height = await asyncio.to_thread(_probe_video, file_path)
    thumb_path = await asyncio.to_thread(_extract_thumbnail, file_path)

    # Clean caption: remove .mp4, no emojis
    caption = filename
    if caption.lower().endswith(".mp4"):
        caption = caption[:-4]
        
    # File name for download must end with .mp4
    save_filename = filename
    if not save_filename.lower().endswith(".mp4"):
        save_filename += ".mp4"

    try:
        # Issue 1: send_video for inline playback
        sent_msg = await client.send_video(
            chat_id=chat_id,
            video=file_path,
            file_name=save_filename,
            caption=caption,
            supports_streaming=True,
            duration=duration,
            width=width,
            height=height,
            thumb=thumb_path,
            progress=tg_progress_cb,
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
                file_name=save_filename,
                caption=caption,
                thumb=thumb_path,
                progress=tg_progress_cb,
            )
        except Exception as exc:
            raise TelegramUploadError(
                f"Telegram fallback upload failed for {filename}: {exc}"
            ) from exc
    except Exception as exc:
        raise TelegramUploadError(
            f"Telegram upload failed for {filename}: {exc}"
        ) from exc

    finally:
        if thumb_path and os.path.exists(thumb_path):
            try:
                os.unlink(thumb_path)
            except OSError:
                pass

    log.info("Uploaded %s to Telegram (chat_id=%d)", filename, chat_id)
    return sent_msg

# ───────────────────────── main entry point ───────────────────────

async def upload_recordings(
    recordings: list[dict],
    access_token: str,
    tg_client: Client,
    chat_id: int,
    progress_cb: Callable | None = None,
    state_manager: "Any" = None,
) -> list[dict]:
    """Download recordings from Graph and upload to Telegram via Producer/Consumer async queue."""
    access_token = access_token.strip()

    results: list[dict] = []
    start_time_all = asyncio.get_event_loop().time()
    total_size_mb = sum(r.get("size_mb", 0) for r in recordings)

    if progress_cb:
        await progress_cb("start", {"total": len(recordings), "total_mb": total_size_mb})

    queue = asyncio.Queue(maxsize=1)

    async def _producer():
        for i, rec in enumerate(recordings):
            filename = rec["name"]
            drive_id = rec["drive_id"]
            item_id = rec["item_id"]
            
            start_time_file = asyncio.get_event_loop().time()
            log.info("Downloading: %s (drive=%s, item=%s)", filename, drive_id, item_id)

            tmp_file = tempfile.NamedTemporaryFile(suffix=".mp4", prefix="teamsleech_", delete=False)
            tmp_path = tmp_file.name
            tmp_file.close()

            try:
                if progress_cb:
                    await progress_cb("file_progress", {
                        "index": i, "name": filename, "percent": 0, "speed_mbps": 0.0
                    })
                
                # Fetching Graph API strictly blocks, wrap in to_thread
                file_size = await asyncio.to_thread(_download_recording, drive_id, item_id, access_token, tmp_path)
                
                log.info("Download complete: %s. Handing to consumer queue...", filename)
                await queue.put({
                    "index": i, "rec": rec, "tmp_path": tmp_path, 
                    "file_size": file_size, "start_time_file": start_time_file
                })
                
            except Exception as e:
                log.error("Download failed for %s: %s", filename, e)
                if progress_cb:
                    await progress_cb("error", {"index": i, "name": filename, "error": str(e)})
                results.append({"name": filename, "success": False, "error": str(e)})
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        
        await queue.put(None) # Sentinel to terminate consumer

    async def _consumer():
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            
            i = item["index"]
            rec = item["rec"]
            tmp_path = item["tmp_path"]
            file_size = item["file_size"]
            start_time_file = item["start_time_file"]
            filename = rec["name"]

            last_progress_time = asyncio.get_event_loop().time()
            last_progress_bytes = 0

            async def _tg_progress(current: int, total: int):
                if total == 0: return
                pct = int((current / total) * 100)
                if pct % 5 == 0 and progress_cb:
                    nonlocal last_progress_time, last_progress_bytes
                    now = asyncio.get_event_loop().time()
                    elapsed_chunk = now - last_progress_time
                    speed_mbps = 0.0
                    if elapsed_chunk > 0:
                        speed_mbps = ((current - last_progress_bytes) / (1024*1024)) / elapsed_chunk
                    
                    last_progress_time = now
                    last_progress_bytes = current
                    
                    await progress_cb("file_progress", {"index": i, "name": filename, "percent": pct, "speed_mbps": speed_mbps})

            try:
                await _upload_to_telegram(tg_client, chat_id, tmp_path, filename, _tg_progress)
                elapsed_file = asyncio.get_event_loop().time() - start_time_file
                
                # Update State Manager directly after a successful upload
                if state_manager and "subject_name" in rec:
                     from datetime import datetime, timezone
                     rec_time_str = f"{rec.get('created', '')}T{rec.get('time', '00:00')}:00+00:00"
                     try:
                         rec_date = datetime.fromisoformat(rec_time_str)
                         current_last = state_manager.get_last_run(rec["subject_name"])
                         if rec_date > current_last:
                             await state_manager.save_last_run(rec["subject_name"], rec_date)
                     except Exception as e:
                         log.warning("Could not set strict datetime for state, using now()")
                         await state_manager.save_last_run(rec["subject_name"])

                if progress_cb:
                    await progress_cb("file_done", {"index": i, "name": filename, "size_mb": file_size / (1024*1024), "elapsed_s": elapsed_file})
                results.append({"name": filename, "success": True, "error": None})

            except Exception as e:
                log.error("Upload Error for %s: %s", filename, e)
                if progress_cb:
                    await progress_cb("error", {"index": i, "name": filename, "error": str(e)})
                results.append({"name": filename, "success": False, "error": str(e)})
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                queue.task_done()

    try:
        producer_task = asyncio.create_task(_producer())
        consumer_task = asyncio.create_task(_consumer())
        await asyncio.gather(producer_task, consumer_task)
    except Exception as e:
        log.error("Queue execution crashed: %s", e)

    if progress_cb:
        await progress_cb("all_done", {"total": len(recordings), "total_mb": total_size_mb, "elapsed_s": asyncio.get_event_loop().time() - start_time_all})

    return results
