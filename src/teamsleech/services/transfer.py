import asyncio
from datetime import datetime
import json
import logging
import os
import subprocess
import tempfile
from typing import Callable

import httpx
from pyrogram import Client
from pyrogram.errors import BadRequest
from pyrogram.types import Message

from teamsleech.core.constants import GRAPH_BASE_URL, CHUNK_SIZE_BYTES
from teamsleech.models.domain import Recording
from teamsleech.services.graph import GraphClient
from teamsleech.services.state import StateManager

log = logging.getLogger("transfer")

class TransferError(Exception):
    pass

class DownloadError(TransferError):
    pass

class TelegramUploadError(TransferError):
    pass

class TransferService:
    def __init__(
        self,
        graph_client: GraphClient,
        state_manager: StateManager,
        tg_client: Client,
        chat_id: int,
    ):
        self.graph = graph_client
        self.state = state_manager
        self.tg = tg_client
        self.chat_id = chat_id

    def _probe_video(self, file_path: str) -> tuple[int, int, int]:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet", "-print_format", "json",
                    "-show_streams", "-show_format", file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            data = json.loads(result.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    w = int(stream.get("width", 1280))
                    h = int(stream.get("height", 720))
                    dur = stream.get("duration")
                    if dur is None:
                        fmt = data.get("format", {})
                        dur = fmt.get("duration", 0)
                    return int(float(dur)), w, h
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            log.warning("ffprobe failed: %s", exc)
        return 0, 1280, 720

    def _extract_thumbnail(self, video_path: str) -> str | None:
        thumb_path = video_path + ".jpg"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", video_path,
                    "-ss", "00:00:02", "-vframes", "1",
                    "-q:v", "2", thumb_path,
                ],
                capture_output=True,
                timeout=20,
                check=True,
            )
            if os.path.exists(thumb_path):
                return thumb_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log.warning("Thumbnail extraction failed: %s", exc)
        return None

    async def _download_recording(
        self, rec: Recording, dest_path: str
    ) -> int:
        url = (
            f"{GRAPH_BASE_URL}/drives/{rec.drive_id}"
            f"/items/{rec.item_id}/content"
        )

        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "GET",
                    url,
                    headers=self.graph.headers,
                    timeout=60.0,
                    follow_redirects=True,
                ) as resp:
                    resp.raise_for_status()
                    total_written = 0
                    with open(dest_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(
                            chunk_size=CHUNK_SIZE_BYTES
                        ):
                            f.write(chunk)
                            total_written += len(chunk)
                    return total_written
            except httpx.RequestError as exc:
                raise DownloadError(
                    f"Graph download failed: {exc}"
                ) from exc

    async def _upload_to_telegram(
        self,
        file_path: str,
        filename: str,
        is_video: bool,
        tg_progress_cb: Callable,
    ) -> Message:
        if not is_video:
            duration, width, height = 0, 0, 0
            thumb_path = None
        else:
            duration, width, height = await asyncio.to_thread(
                self._probe_video, file_path
            )
            thumb_path = await asyncio.to_thread(
                self._extract_thumbnail, file_path
            )

        ext = ""
        if "." in filename:
            ext = "." + filename.split(".")[-1].lower()
            caption = filename[: -len(ext)]
        else:
            caption = filename

        save_filename = filename
        if not save_filename.lower().endswith(ext):
            save_filename += ext

        try:
            if not is_video:
                sent_msg = await self.tg.send_document(
                    chat_id=self.chat_id,
                    document=file_path,
                    file_name=save_filename,
                    caption=caption,
                    progress=tg_progress_cb,
                )
            else:
                sent_msg = await self.tg.send_video(
                    chat_id=self.chat_id,
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
            if is_video:
                log.warning(
                    "send_video rejected — falling back to send_document"
                )
                sent_msg = await self.tg.send_document(
                    chat_id=self.chat_id,
                    document=file_path,
                    file_name=save_filename,
                    caption=caption,
                    thumb=thumb_path,
                    progress=tg_progress_cb,
                )
            else:
                raise
        except Exception as exc:
            raise TelegramUploadError(
                f"Upload failed: {exc}"
            ) from exc
        finally:
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.unlink(thumb_path)
                except OSError:
                    pass

        return sent_msg

    async def upload_recordings(
        self,
        recordings: list[Recording],
        progress_cb: Callable | None = None,
    ) -> list[dict]:
        results: list[dict] = []
        start_time_all = asyncio.get_event_loop().time()
        total_size_mb = sum(r.size_mb for r in recordings)

        if progress_cb:
            await progress_cb(
                "start",
                {"total": len(recordings), "total_mb": total_size_mb},
            )

        queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=1)

        async def _producer():
            for i, rec in enumerate(recordings):
                start_time_file = asyncio.get_event_loop().time()
                log.info("Downloading: %s", rec.name)

                ext = (
                    ".mp4"
                    if rec.is_video
                    else (
                        ".pdf"
                        if ".pdf" in rec.name.lower()
                        else ""
                    )
                )
                if not ext and "." in rec.name:
                    ext = "." + rec.name.split(".")[-1]

                tmp_file = tempfile.NamedTemporaryFile(
                    suffix=ext, prefix="teamsleech_", delete=False
                )
                tmp_path = tmp_file.name
                tmp_file.close()

                try:
                    if progress_cb:
                        await progress_cb(
                            "file_progress",
                            {
                                "index": i,
                                "name": rec.name,
                                "percent": 0,
                                "speed_mbps": 0.0,
                            },
                        )

                    file_size = await self._download_recording(
                        rec, tmp_path
                    )

                    await queue.put(
                        {
                            "index": i,
                            "rec": rec,
                            "tmp_path": tmp_path,
                            "file_size": file_size,
                            "start_time_file": start_time_file,
                        }
                    )
                except Exception as e:
                    log.error(
                        "Download failed for %s: %s", rec.name, e
                    )
                    if progress_cb:
                        await progress_cb(
                            "error",
                            {
                                "index": i,
                                "name": rec.name,
                                "error": str(e),
                            },
                        )
                    results.append(
                        {
                            "name": rec.name,
                            "success": False,
                            "error": str(e),
                        }
                    )
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            await queue.put(None)

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
                last_progress_time = asyncio.get_event_loop().time()
                last_progress_bytes = 0

                async def _tg_progress(
                    current: int,
                    total: int,
                    _i=i,
                    _rec=rec,
                ):
                    if total == 0:
                        return
                    pct = int((current / total) * 100)
                    if pct % 5 == 0 and progress_cb:
                        nonlocal last_progress_time, last_progress_bytes
                        now = asyncio.get_event_loop().time()
                        elapsed_chunk = now - last_progress_time
                        speed_mbps = (
                            ((current - last_progress_bytes)
                             / (1024 * 1024))
                            / elapsed_chunk
                            if elapsed_chunk > 0
                            else 0.0
                        )
                        last_progress_time, last_progress_bytes = (
                            now,
                            current,
                        )
                        await progress_cb(
                            "file_progress",
                            {
                                "index": _i,
                                "name": _rec.name,
                                "percent": pct,
                                "speed_mbps": speed_mbps,
                            },
                        )

                try:
                    await self._upload_to_telegram(
                        tmp_path, rec.name, rec.is_video, _tg_progress
                    )
                    elapsed_file = (
                        asyncio.get_event_loop().time()
                        - start_time_file
                    )

                    rec_time_str = (
                        f"{rec.created}T{rec.time or '00:00'}:00+00:00"
                    )
                    try:
                        rec_date = datetime.fromisoformat(rec_time_str)
                        if rec_date > self.state.get_last_run(
                            rec.subject_name
                        ):
                            await self.state.save_last_run(
                                rec.subject_name, rec_date
                            )
                            await self.state.save_last_lecture(
                                rec.subject_name,
                                self.state.get_last_lecture(
                                    rec.subject_name
                                )
                                + 1,
                            )
                    except ValueError:
                        await self.state.save_last_run(
                            rec.subject_name
                        )
                        await self.state.save_last_lecture(
                            rec.subject_name,
                            self.state.get_last_lecture(
                                rec.subject_name
                            )
                            + 1,
                        )

                    if progress_cb:
                        await progress_cb(
                            "file_done",
                            {
                                "index": i,
                                "name": rec.name,
                                "size_mb": file_size / (1024 * 1024),
                                "elapsed_s": elapsed_file,
                            },
                        )
                    results.append(
                        {
                            "name": rec.name,
                            "success": True,
                            "error": None,
                        }
                    )
                except Exception as e:
                    if progress_cb:
                        await progress_cb(
                            "error",
                            {
                                "index": i,
                                "name": rec.name,
                                "error": str(e),
                            },
                        )
                    results.append(
                        {
                            "name": rec.name,
                            "success": False,
                            "error": str(e),
                        }
                    )
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    queue.task_done()

        await asyncio.gather(
            asyncio.create_task(_producer()),
            asyncio.create_task(_consumer()),
        )

        if progress_cb:
            await progress_cb(
                "all_done",
                {
                    "total": len(recordings),
                    "total_mb": total_size_mb,
                    "elapsed_s": asyncio.get_event_loop().time()
                    - start_time_all,
                },
            )

        return results
