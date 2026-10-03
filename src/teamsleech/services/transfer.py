import asyncio
import base64
import json
import logging
import os
import subprocess
import tempfile
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

import httpx
from pyrogram import Client
from pyrogram.errors import BadRequest, RPCError
from pyrogram.types import Message
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from teamsleech.core.config import settings
from teamsleech.core.constants import CHUNK_SIZE_BYTES, GRAPH_BASE_URL
from teamsleech.core.retry import retry_tg
from teamsleech.models.domain import Recording
from teamsleech.services.auth import authenticate_sharepoint
from teamsleech.services.cookies import cookie_header, load_cookies
from teamsleech.services.graph import GraphClient
from teamsleech.services.state import StateManager

log = logging.getLogger("transfer")

THUMBNAIL_TIMESTAMP = "00:00:02"

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
        self._sp_tokens: dict[str, str | None] = {}

    _retry_download = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
        retry=retry_if_exception_type(DownloadError),
        reraise=True,
    )

    @retry_tg
    async def _tg_send_document(
        self, chat_id, file_path, file_name, caption, thumb, progress
    ) -> Message:
        return await self.tg.send_document(
            chat_id=chat_id, document=file_path,
            file_name=file_name, caption=caption,
            thumb=thumb, progress=progress,
        )

    @retry_tg
    async def _tg_send_video(
        self, chat_id, file_path, file_name, caption,
        duration, width, height, thumb, progress,
    ) -> Message:
        return await self.tg.send_video(
            chat_id=chat_id, video=file_path,
            file_name=file_name, caption=caption,
            supports_streaming=True,
            duration=duration, width=width, height=height,
            thumb=thumb, progress=progress,
        )

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
            fmt = data.get("format", {})
            dur = fmt.get("duration", 0)
            return int(float(dur)), 1280, 720
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError, TimeoutError) as exc:
            log.warning("ffprobe failed: %s", exc)
        return 0, 1280, 720

    def _extract_thumbnail(self, video_path: str) -> str | None:
        thumb_path = video_path + ".jpg"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", video_path,
                    "-ss", THUMBNAIL_TIMESTAMP, "-vframes", "1",
                    "-q:v", "2", thumb_path,
                ],
                capture_output=True,
                timeout=20,
                check=True,
            )
            if os.path.exists(thumb_path):
                return thumb_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            log.warning("Thumbnail extraction failed: %s", exc)
        return None

    async def _sharepoint_token(self, host: str) -> str | None:
        if host not in self._sp_tokens:
            self._sp_tokens[host] = await authenticate_sharepoint(host)
        return self._sp_tokens[host]

    def _log_token_audience(self, token: str, host: str) -> None:
        try:
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            claims = json.loads(base64.b64decode(payload_b64).decode())
            log.info(
                "SharePoint token for %s: aud=%s scp=%s",
                host, claims.get("aud"), claims.get("scp"),
            )
        except Exception as exc:
            log.warning("Could not inspect SharePoint token: %s", exc)

    def _download_candidates(
        self, download_url: str, sp_token: str | None
    ) -> list[tuple[str, str, dict[str, str] | None]]:
        """Ordered (label, url, headers) attempts. Browser cookies first —
        proven path (same session as a working browser); token endpoints
        after; anonymous last."""
        candidates = []
        cookies = load_cookies(settings.sp_cookies_json)
        if cookies:
            candidates.append(
                (
                    "download.aspx (browser cookies)",
                    download_url,
                    {"Cookie": cookie_header(cookies)},
                )
            )

        bearer = {"Authorization": f"Bearer {sp_token}"} if sp_token else None
        if not sp_token:
            candidates.append(("download.aspx (anonymous)", download_url, None))
            return candidates

        parts = urlsplit(download_url)
        unique_id = parse_qs(parts.query).get("UniqueId", [None])[0]
        marker = "/_layouts/15/download.aspx"
        if unique_id and marker in parts.path:
            site_path = parts.path.split(marker)[0]
            api_url = (
                f"{parts.scheme}://{parts.netloc}{site_path}"
                f"/_api/web/GetFileById('{unique_id}')/$value"
            )
            candidates.append(("SharePoint REST $value", api_url, bearer))
        candidates.append(("download.aspx (user token)", download_url, bearer))
        return candidates

    @_retry_download
    async def _download_recording(
        self,
        rec: Recording,
        dest_path: str,
        dl_cb: Callable | None = None,
    ) -> int:
        graph_url = (
            f"{GRAPH_BASE_URL}/drives/{rec.drive_id}"
            f"/items/{rec.item_id}/content"
        )

        async with httpx.AsyncClient() as client:
            # Step 1: ask Graph, do NOT auto-follow. Graph answers 302
            # with a pre-authenticated SharePoint download URL in
            # Location. Following automatically risks forwarding the
            # Graph Bearer / Accept headers to SharePoint (-> 401).
            try:
                graph_resp = await client.get(
                    graph_url,
                    headers=self.graph.headers,
                    timeout=60.0,
                    follow_redirects=False,
                )
            except httpx.RequestError as exc:
                raise DownloadError(
                    f"Graph download request failed for {rec.name}: {exc}"
                ) from exc

            if graph_resp.status_code in (301, 302, 303, 307, 308):
                download_url = graph_resp.headers.get("Location")
                if not download_url:
                    raise DownloadError(
                        f"Graph redirect [{graph_resp.status_code}]"
                        f" missing Location for {rec.name}"
                    )
                log.info(
                    "Graph redirect for %s -> %s",
                    rec.name, download_url.split("?")[0],
                )
            elif graph_resp.status_code == 200:
                # Small files may come back inline — write body directly.
                with open(dest_path, "wb") as f:
                    f.write(graph_resp.content)
                return len(graph_resp.content)
            else:
                try:
                    body = graph_resp.text[:300]
                except Exception:
                    body = "<unreadable body>"
                raise DownloadError(
                    f"Graph denied content [{graph_resp.status_code}]"
                    f" for {rec.name}: {body}"
                )

            # Step 2: fetch bytes in the user's own SharePoint context
            # when possible, else anonymously via the pre-authed URL.
            host = urlsplit(download_url).hostname or ""
            sp_token = await self._sharepoint_token(host) if host else None
            if sp_token:
                self._log_token_audience(sp_token, host)
                log.info("Downloading %s with user SharePoint token.", rec.name)
            else:
                log.info(
                    "Downloading %s anonymously (no SharePoint token).", rec.name
                )
            failures: list[str] = []
            for label, url, headers in self._download_candidates(
                download_url, sp_token
            ):
                log.info("Trying %s for %s.", label, rec.name)
                try:
                    async with client.stream(
                        "GET",
                        url,
                        headers=headers,
                        timeout=60.0,
                        follow_redirects=True,
                    ) as resp:
                        resp.raise_for_status()
                        total_written = 0
                        last_pct = -1
                        last_mb_mark = 0
                        try:
                            total = int(resp.headers.get("content-length") or 0) or None
                        except (TypeError, ValueError):
                            total = None
                        with open(dest_path, "wb") as f:
                            async for chunk in resp.aiter_bytes(
                                chunk_size=CHUNK_SIZE_BYTES
                            ):
                                f.write(chunk)
                                total_written += len(chunk)
                                if dl_cb is not None:
                                    if total:
                                        pct = int(total_written / total * 100)
                                        if pct >= last_pct + 5 or pct >= 100:
                                            last_pct = pct
                                            await dl_cb(total_written, total)
                                    else:
                                        mb = total_written // (10 * 1024 * 1024)
                                        if mb > last_mb_mark:
                                            last_mb_mark = mb
                                            await dl_cb(total_written, None)
                            if dl_cb is not None:
                                await dl_cb(total_written, total, done=True)
                        return total_written
                except httpx.HTTPStatusError as exc:
                    failures.append(f"{label} [{exc.response.status_code}]")
                    log.warning("%s failed for %s: %s", label, rec.name, exc)
                    continue
                except httpx.HTTPError as exc:
                    failures.append(f"{label} ({exc})")
                    log.warning("%s errored for %s: %s", label, rec.name, exc)
                    continue
            cookies_tried = any(
                f.startswith("download.aspx (browser cookies)") for f in failures
            )
            if cookies_tried:
                hint = (
                    "browser cookies rejected too — session expired,"
                    " re-export SP_COOKIES_JSON from a logged-in browser"
                )
            elif sp_token:
                hint = (
                    "user-context token denied on REST + download.aspx — account"
                    " lacks download rights or Block-Download policy applies;"
                    " set SP_COOKIES_JSON for the proven cookie path"
                )
            else:
                hint = (
                    "check Conditional Access / Block-Download"
                    " policy / site permissions for the service account;"
                    " set SP_COOKIES_JSON for the proven cookie path"
                )
            raise DownloadError(
                f"SharePoint download failed for {rec.name}"
                f" ({' ; '.join(failures)}): {hint}."
            )

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
                sent_msg = await self._tg_send_document(
                    self.chat_id, file_path, save_filename, caption, None, tg_progress_cb,
                )
            else:
                sent_msg = await self._tg_send_video(
                    self.chat_id, file_path, save_filename, caption,
                    duration, width, height, thumb_path, tg_progress_cb,
                )
        except BadRequest:
            if is_video:
                log.warning(
                    "send_video rejected — falling back to send_document"
                )
                sent_msg = await self._tg_send_document(
                    self.chat_id, file_path, save_filename, caption, thumb_path, tg_progress_cb,
                )
            else:
                raise
        except (RPCError, TimeoutError, ConnectionError, OSError) as exc:
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

    async def _report_progress(
        self,
        current: int,
        total: int,
        index: int,
        name: str,
        progress_cb: Callable | None,
    ) -> None:
        if total == 0:
            return
        pct = int((current / total) * 100)
        if (pct % 5 == 0 or pct >= 100) and progress_cb:
            now = asyncio.get_event_loop().time()
            elapsed_chunk = now - self._progress_last_time
            speed_mbps = (
                ((current - self._progress_last_bytes) / (1024 * 1024))
                / elapsed_chunk
                if elapsed_chunk > 0
                else 0.0
            )
            self._progress_last_time, self._progress_last_bytes = now, current
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
        queue: asyncio.Queue[dict | None],
        results: list[dict],
        progress_cb: Callable | None,
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
            self._progress_last_time = asyncio.get_event_loop().time()
            self._progress_last_bytes = 0

            async def _tg_progress(current: int, total: int, _i=i, _name=rec.name):
                await self._report_progress(current, total, _i, _name, progress_cb)

            try:
                await self._upload_to_telegram(
                    tmp_path, rec.name, rec.is_video, _tg_progress
                )
                elapsed_file = (
                    asyncio.get_event_loop().time() - start_time_file
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
                    {"name": rec.name, "success": True, "error": None, "rec": rec}
                )
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
                results.append(
                    {"name": rec.name, "success": False, "error": str(e), "rec": rec}
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                queue.task_done()

    async def _producer_loop(
        self,
        recordings: list[Recording],
        queue: asyncio.Queue[dict | None],
        results: list[dict],
        progress_cb: Callable | None,
    ) -> None:
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
                async def _dl_emit(
                    written: int, total: int | None, done: bool = False,
                    _i=i, _name=rec.name, _t0=start_time_file,
                ):
                    if not progress_cb:
                        return
                    elapsed = asyncio.get_event_loop().time() - _t0
                    payload: dict = {
                        "index": _i,
                        "name": _name,
                        "written_mb": written / (1024 * 1024),
                        "elapsed_s": elapsed,
                        "done": done,
                    }
                    if total:
                        payload["percent"] = int(written / total * 100)
                        payload["speed_mbps"] = (
                            (written / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
                        )
                    await progress_cb("dl_progress", payload)

                if progress_cb:
                    await progress_cb(
                        "dl_start", {"index": i, "name": rec.name}
                    )

                file_size = await self._download_recording(
                    rec, tmp_path, _dl_emit
                )

                if progress_cb:
                    await progress_cb(
                        "dl_done",
                        {
                            "index": i,
                            "name": rec.name,
                            "size_mb": file_size / (1024 * 1024),
                        },
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
            except DownloadError as e:
                log.error("Download failed for %s: %s", rec.name, e)
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

        await queue.put(None)

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

        await asyncio.gather(
            asyncio.create_task(self._producer_loop(recordings, queue, results, progress_cb)),
            asyncio.create_task(self._consumer_loop(queue, results, progress_cb)),
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
