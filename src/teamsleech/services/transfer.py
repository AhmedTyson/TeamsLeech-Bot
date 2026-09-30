import asyncio
import json
import logging
import os
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any, cast
from urllib.parse import urljoin, urlparse

import httpx
from pyrogram.client import Client
from pyrogram.errors import BadRequest
from pyrogram.errors.rpc_error import RPCError
from pyrogram.types import Message

from teamsleech.core.constants import (
    CHUNK_SIZE_BYTES,
    GRAPH_BASE_URL,
    TELEGRAM_MAX_FILE_BYTES,
)
from teamsleech.core.retry import retry_on, retry_tg
from teamsleech.models.domain import Recording
from teamsleech.services.graph import GraphClient, quote_id
from teamsleech.services.state import StateManager

log = logging.getLogger("transfer")

THUMBNAIL_TIMESTAMP = "00:00:02"

ProgressCallback = Callable[..., Any]


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
        self._progress_last_time: float = 0.0
        self._progress_last_bytes: int = 0
        self._progress_last_pct: int = -1

    _retry_download = retry_on(DownloadError)

    @retry_tg
    async def _tg_send_document(
        self,
        chat_id: int,
        file_path: str,
        file_name: str,
        caption: str,
        thumb: str | None,
        progress: ProgressCallback,
    ) -> Message:
        kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "document": file_path,
            "file_name": file_name,
            "caption": caption,
            "progress": progress,
        }
        if thumb is not None:
            kwargs["thumb"] = thumb
        return cast(Message, await self.tg.send_document(**kwargs))

    @retry_tg
    async def _tg_send_video(
        self,
        chat_id: int,
        file_path: str,
        file_name: str,
        caption: str,
        duration: int,
        width: int,
        height: int,
        thumb: str | None,
        progress: ProgressCallback,
    ) -> Message:
        kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "video": file_path,
            "file_name": file_name,
            "caption": caption,
            "supports_streaming": True,
            "duration": duration,
            "width": width,
            "height": height,
            "progress": progress,
        }
        if thumb is not None:
            kwargs["thumb"] = thumb
        return cast(Message, await self.tg.send_video(**kwargs))

    def _probe_video(self, file_path: str) -> tuple[int, int, int]:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_streams",
                    "-show_format",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
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
            fmt = data.get("format", {})
            dur = fmt.get("duration", 0)
            return int(float(dur)), 1280, 720
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
            OSError,
            TimeoutError,
        ) as exc:
            log.warning("ffprobe failed: %s", exc)
        return 0, 1280, 720

    def _extract_thumbnail(self, video_path: str) -> str | None:
        thumb_path = video_path + ".jpg"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    video_path,
                    "-ss",
                    THUMBNAIL_TIMESTAMP,
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    thumb_path,
                ],
                capture_output=True,
                timeout=20,
                check=True,
                shell=False,
            )
            if os.path.exists(thumb_path):
                return thumb_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            log.warning("Thumbnail extraction failed: %s", exc)
        return None

    @staticmethod
    def _redirect_target(
        resp: httpx.Response,
        rec_name: str,
        target: str,
        headers: dict[str, str],
    ) -> str | None:
        """Next URL if `resp` is a redirect, else None.

        Mutates `headers` to strip the Bearer token when leaving the
        Graph host — pre-signed content URLs carry their own auth.
        """
        if resp.status_code not in (301, 302, 303, 307, 308):
            return None
        location = resp.headers.get("location")
        if not location:
            msg = f"Graph download redirect for {rec_name} " "missing Location header."
            raise DownloadError(msg)
        nxt: str = urljoin(target, location)
        if urlparse(nxt).scheme != "https":
            msg = f"Graph download redirect for {rec_name} is not HTTPS."
            raise DownloadError(msg)
        if urlparse(nxt).hostname != urlparse(GRAPH_BASE_URL).hostname:
            headers.clear()
            headers["Accept"] = "application/json"
        return nxt

    @staticmethod
    async def _store_stream(resp: httpx.Response, rec: Recording, dest_path: str) -> int:
        declared = resp.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > TELEGRAM_MAX_FILE_BYTES:
                    msg = f"File {rec.name} ({declared} bytes) exceeds " "Telegram 2 GB limit."
                    raise DownloadError(msg)
            except ValueError:
                pass
        total_written = 0
        with open(dest_path, "wb") as f:  # noqa: ASYNC101 - local temp file, chunked writes
            async for chunk in resp.aiter_bytes(chunk_size=CHUNK_SIZE_BYTES):
                f.write(chunk)
                total_written += len(chunk)
                if total_written > TELEGRAM_MAX_FILE_BYTES:
                    msg = f"File {rec.name} exceeds Telegram 2 GB limit."
                    raise DownloadError(msg)
        return total_written

    async def _download_with_redirects(self, rec: Recording, url: str, dest_path: str) -> int:
        target = url
        headers = dict(self.graph.headers)
        for _ in range(4):
            async with self.graph.client.stream(
                "GET",
                target,
                headers=headers,
                timeout=60.0,
                follow_redirects=False,
            ) as resp:
                nxt = self._redirect_target(resp, rec.name, target, headers)
                if nxt is None:
                    resp.raise_for_status()
                    return await self._store_stream(resp, rec, dest_path)
                target = nxt
        msg = f"Graph download for {rec.name} exceeded redirect limit."
        raise DownloadError(msg)

    @_retry_download
    async def _download_recording(self, rec: Recording, dest_path: str) -> int:
        url = (
            f"{GRAPH_BASE_URL}/drives/{quote_id(rec.drive_id)}"
            f"/items/{quote_id(rec.item_id)}/content"
        )

        try:
            downloaded = await self._download_with_redirects(rec, url, dest_path)
        except DownloadError:
            raise
        except httpx.HTTPStatusError as exc:
            msg = f"Graph download failed " f"[{exc.response.status_code}]: {exc}"
            raise DownloadError(msg) from exc
        except httpx.RequestError as exc:
            msg = f"Graph download failed: {exc}"
            raise DownloadError(msg) from exc
        else:
            return downloaded

    async def _upload_to_telegram(
        self,
        file_path: str,
        filename: str,
        is_video: bool,
        tg_progress_cb: ProgressCallback,
    ) -> Message:
        thumb_path: str | None = None
        if not is_video:
            duration, width, height = 0, 0, 0
        else:
            duration, width, height = await asyncio.to_thread(self._probe_video, file_path)
            thumb_path = await asyncio.to_thread(self._extract_thumbnail, file_path)

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
                sent_msg = await self._tg_send_document(
                    self.chat_id,
                    file_path,
                    save_filename,
                    caption,
                    None,
                    tg_progress_cb,
                )
            else:
                sent_msg = await self._tg_send_video(
                    self.chat_id,
                    file_path,
                    save_filename,
                    caption,
                    duration,
                    width,
                    height,
                    thumb_path,
                    tg_progress_cb,
                )
        except BadRequest:
            if is_video:
                log.warning("send_video rejected — falling back to send_document")
                sent_msg = await self._tg_send_document(
                    self.chat_id,
                    file_path,
                    save_filename,
                    caption,
                    thumb_path,
                    tg_progress_cb,
                )
            else:
                raise
        except (RPCError, TimeoutError, ConnectionError, OSError) as exc:
            msg = f"Upload failed: {exc}"
            raise TelegramUploadError(msg) from exc
        finally:
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.unlink(thumb_path)
                except OSError:
                    pass

        return sent_msg

    async def _report_progress(
        self,
        current: int,
        total: int,
        index: int,
        name: str,
        progress_cb: ProgressCallback | None,
    ) -> None:
        if total == 0:
            return
        pct = int((current / total) * 100)
        if pct == self._progress_last_pct:
            return
        if pct % 5 == 0 and progress_cb:
            now = asyncio.get_running_loop().time()
            elapsed_chunk = now - self._progress_last_time
            if elapsed_chunk <= 1e-6:
                speed_mbps = 0.0
            else:
                speed_mbps = ((current - self._progress_last_bytes) / (1024 * 1024)) / elapsed_chunk
            self._progress_last_time = now
            self._progress_last_bytes = current
            self._progress_last_pct = pct
            await progress_cb(
                "file_progress",
                {
                    "index": index,
                    "name": name,
                    "percent": pct,
                    "speed_mbps": speed_mbps,
                },
            )

    async def _consumer_loop(
        self,
        queue: asyncio.Queue[dict[str, Any] | None],
        results: list[dict[str, Any]],
        progress_cb: ProgressCallback | None,
    ) -> None:
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
            self._progress_last_time = asyncio.get_running_loop().time()
            self._progress_last_bytes = 0
            self._progress_last_pct = -1

            async def _tg_progress(
                current: int, total: int, _i: int = i, _name: str = rec.name
            ) -> None:
                await self._report_progress(current, total, _i, _name, progress_cb)

            try:
                await self._upload_to_telegram(tmp_path, rec.name, rec.is_video, _tg_progress)
                elapsed_file = asyncio.get_running_loop().time() - start_time_file

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
                results.append({"name": rec.name, "success": True, "error": None, "rec": rec})
            except (TelegramUploadError, OSError) as e:
                if progress_cb:
                    await progress_cb(
                        "error",
                        {
                            "index": i,
                            "name": rec.name,
                            "error": str(e),
                        },
                    )
                results.append({"name": rec.name, "success": False, "error": str(e), "rec": rec})
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                queue.task_done()

    async def _producer_loop(
        self,
        recordings: list[Recording],
        queue: asyncio.Queue[dict[str, Any] | None],
        results: list[dict[str, Any]],
        progress_cb: ProgressCallback | None,
    ) -> None:
        try:
            for i, rec in enumerate(recordings):
                start_time_file = asyncio.get_running_loop().time()
                log.info("Downloading: %s", rec.name)

                ext = ".mp4" if rec.is_video else (".pdf" if ".pdf" in rec.name.lower() else "")
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

                    file_size = await self._download_recording(rec, tmp_path)

                    await queue.put(
                        {
                            "index": i,
                            "rec": rec,
                            "tmp_path": tmp_path,
                            "file_size": file_size,
                            "start_time_file": start_time_file,
                        }
                    )
                except DownloadError as e:
                    log.exception("Download failed for %s", rec.name)
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
                        {"name": rec.name, "success": False, "error": str(e), "rec": rec}
                    )
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                except Exception as e:
                    log.exception("Unexpected download error for %s", rec.name)
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
                        {"name": rec.name, "success": False, "error": str(e), "rec": rec}
                    )
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
        finally:
            await queue.put(None)

    async def upload_recordings(
        self,
        recordings: list[Recording],
        progress_cb: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        start_time_all = asyncio.get_running_loop().time()
        total_size_mb = sum(r.size_mb for r in recordings)

        if progress_cb:
            await progress_cb(
                "start",
                {"total": len(recordings), "total_mb": total_size_mb},
            )

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=1)

        producer = asyncio.create_task(self._producer_loop(recordings, queue, results, progress_cb))
        consumer = asyncio.create_task(self._consumer_loop(queue, results, progress_cb))
        try:
            await asyncio.gather(producer, consumer)
        finally:
            for task in (producer, consumer):
                if not task.done():
                    task.cancel()
            await asyncio.gather(producer, consumer, return_exceptions=True)

        if progress_cb:
            await progress_cb(
                "all_done",
                {
                    "total": len(recordings),
                    "total_mb": total_size_mb,
                    "elapsed_s": asyncio.get_running_loop().time() - start_time_all,
                },
            )

        return results
