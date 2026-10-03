from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from teamsleech.models.domain import Recording
from teamsleech.services.transfer import (
    DownloadError,
    TelegramUploadError,
    TransferError,
    TransferService,
)


@pytest.fixture
def transfer_service(graph_client, mock_pyrogram_client):
    state = AsyncMock()
    return TransferService(graph_client, state, mock_pyrogram_client, 67890)


@pytest.fixture
def sample_recordings():
    return [
        Recording(
            name="lecture1.mp4", size_mb=100.0, created="2024-01-15",
            time="10:00", duration_ms=1_800_000, drive_id="d1",
            item_id="i1", team_name="CS-A", subject_name="Math",
            is_video=True,
        ),
        Recording(
            name="notes.pdf", size_mb=5.0, created="2024-01-15",
            time="10:00", duration_ms=0, drive_id="d1",
            item_id="i2", team_name="CS-A", subject_name="Math",
            is_video=False,
        ),
    ]


class TestProbeVideo:
    def test_probe_video_success(self, transfer_service):
        fake_stdout = (
            '{"streams": [{"codec_type": "video", "width": 1920, '
            '"height": 1080, "duration": "60.5"}], "format": {}}'
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_stdout)
            dur, w, h = transfer_service._probe_video("/fake/path.mp4")
        assert dur == 60
        assert w == 1920
        assert h == 1080

    def test_probe_video_no_streams(self, transfer_service):
        fake_stdout = '{"streams": [], "format": {"duration": "30"}}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_stdout)
            dur, w, h = transfer_service._probe_video("/fake/path.mp4")
        assert dur == 30
        assert w == 1280
        assert h == 720

    def test_probe_video_failure(self, transfer_service):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ffprobe not found")
            dur, w, h = transfer_service._probe_video("/fake/path.mp4")
        assert (dur, w, h) == (0, 1280, 720)

    def test_probe_video_timeout(self, transfer_service):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = TimeoutError("ffprobe timed out")
            dur, w, h = transfer_service._probe_video("/fake/path.mp4")
        assert (dur, w, h) == (0, 1280, 720)


class TestExtractThumbnail:
    def test_extract_success(self, transfer_service):
        with (
            patch("subprocess.run") as mock_run,
            patch("os.path.exists") as mock_exists,
        ):
            mock_run.return_value = MagicMock()
            mock_exists.return_value = True
            result = transfer_service._extract_thumbnail("/fake/path.mp4")
        assert result == "/fake/path.mp4.jpg"

    def test_extract_missing_file(self, transfer_service):
        with (
            patch("subprocess.run") as mock_run,
            patch("os.path.exists") as mock_exists,
        ):
            mock_run.return_value = MagicMock()
            mock_exists.return_value = False
            result = transfer_service._extract_thumbnail("/fake/path.mp4")
        assert result is None

    def test_extract_failure(self, transfer_service):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ffmpeg not found")
            result = transfer_service._extract_thumbnail("/fake/path.mp4")
        assert result is None


class TestDownloadRecording:
    @pytest.fixture(autouse=True)
    def _no_sp_token(self):
        with patch(
            "teamsleech.services.transfer.authenticate_sharepoint",
            AsyncMock(return_value=None),
        ):
            yield
    def _mock_client(self, mock_cls, graph_resp=None, dl_resp=None,
                     get_side_effect=None, stream_side_effect=None):
        mock_client = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        if get_side_effect is not None:
            mock_client.get = AsyncMock(side_effect=get_side_effect)
        else:
            mock_client.get = AsyncMock(return_value=graph_resp)
        if stream_side_effect is not None:
            mock_client.stream = MagicMock(side_effect=stream_side_effect)
        elif dl_resp is not None:
            mock_client.stream = MagicMock(return_value=dl_resp)
        return mock_client

    def _graph_redirect(self, location="https://tenant.sharepoint.com/sites/x/_layouts/15/download.aspx?UniqueId=abc&tempauth=tok"):
        resp = MagicMock()
        resp.status_code = 302
        resp.headers = {"Location": location}
        return resp

    def _dl_resp(self, chunk=b"x" * 1024, status_error=None, stream_gen=None):
        resp = AsyncMock()
        resp.__aenter__.return_value = resp
        resp.status_code = 401 if status_error else 200
        if status_error is not None:
            resp.raise_for_status = MagicMock(side_effect=status_error)
        else:
            resp.raise_for_status = MagicMock()
        if stream_gen is not None:
            resp.aiter_bytes = MagicMock(side_effect=lambda **kw: stream_gen())
        else:
            async def _iter():
                yield chunk
            resp.aiter_bytes = MagicMock(return_value=_iter())
        return resp

    async def test_download_success(self, transfer_service, sample_recordings, tmp_path):
        chunk = b"x" * 1024
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = self._mock_client(
                mock_cls,
                graph_resp=self._graph_redirect(),
                dl_resp=self._dl_resp(chunk),
            )
            size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        # Step 1 goes to Graph WITH auth; step 2 to SharePoint WITHOUT auth.
        _, graph_kwargs = mock_client.get.await_args
        assert graph_kwargs["headers"]["Authorization"] == "Bearer fake_token"
        _, stream_kwargs = mock_client.stream.call_args
        assert stream_kwargs.get("headers") is None

    async def test_download_network_error(self, transfer_service, sample_recordings, tmp_path):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        with patch("httpx.AsyncClient") as mock_cls:
            self._mock_client(
                mock_cls,
                get_side_effect=httpx.RequestError("Connection refused"),
            )
            with pytest.raises(DownloadError, match="Connection refused"):
                await transfer_service._download_recording(rec, dest)

    async def test_download_stream_error_midway(self, transfer_service, sample_recordings, tmp_path):
        """Simulate stream failing mid-download after some chunks."""
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")

        async def fail_after_one():
            yield b"x" * 1024
            raise httpx.RequestError("Stream interrupted")

        with patch("httpx.AsyncClient") as mock_cls:
            self._mock_client(
                mock_cls,
                graph_resp=self._graph_redirect(),
                dl_resp=self._dl_resp(stream_gen=fail_after_one),
            )
            with pytest.raises(DownloadError, match="Stream interrupted"):
                await transfer_service._download_recording(rec, dest)

    async def test_graph_denied_reports_permission_hint(self, transfer_service, sample_recordings, tmp_path):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        graph_resp = MagicMock()
        graph_resp.status_code = 401
        graph_resp.text = "Unauthorized"
        with patch("httpx.AsyncClient") as mock_cls:
            self._mock_client(mock_cls, graph_resp=graph_resp)
            with pytest.raises(DownloadError, match=r"Graph denied content \[401\]"):
                await transfer_service._download_recording(rec, dest)

    async def test_redirect_missing_location(self, transfer_service, sample_recordings, tmp_path):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        graph_resp = MagicMock()
        graph_resp.status_code = 302
        graph_resp.headers = {}
        with patch("httpx.AsyncClient") as mock_cls:
            self._mock_client(mock_cls, graph_resp=graph_resp)
            with pytest.raises(DownloadError, match="missing Location"):
                await transfer_service._download_recording(rec, dest)

    async def test_sharepoint_401_wrapped_as_download_error(self, transfer_service, sample_recordings, tmp_path):
        """Regression: SharePoint 401 must surface as DownloadError (retryable), not raw HTTPStatusError."""
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        dl_url = "https://commercehelwanedu.sharepoint.com/sites/x/_layouts/15/download.aspx?UniqueId=abc"
        request = httpx.Request("GET", dl_url)
        status_error = httpx.HTTPStatusError(
            "Client error '401 Unauthorized' for url "
            f"'{dl_url}'",
            request=request,
            response=httpx.Response(401, request=request),
        )
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = self._mock_client(
                mock_cls,
                graph_resp=self._graph_redirect(location=dl_url + "&tempauth=tok"),
                dl_resp=self._dl_resp(status_error=status_error),
            )
            with pytest.raises(DownloadError, match=r"download\.aspx \(anonymous\) \[401\]"):
                await transfer_service._download_recording(rec, dest)
            # SharePoint fetch must not carry the Graph Bearer.
            _, stream_kwargs = mock_client.stream.call_args
            assert stream_kwargs.get("headers") is None

    async def test_download_uses_sharepoint_token_when_available(
        self, transfer_service, sample_recordings, tmp_path
    ):
        chunk = b"x" * 1024
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        with (
            patch(
                "teamsleech.services.transfer.authenticate_sharepoint",
                AsyncMock(return_value="sp_at"),
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_client = self._mock_client(
                mock_cls,
                graph_resp=self._graph_redirect(),
                dl_resp=self._dl_resp(chunk),
            )
            size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        first_call = mock_client.stream.call_args_list[0]
        assert "GetFileById" in first_call.args[1]
        assert first_call.args[1].endswith("/$value")
        assert first_call.kwargs["headers"] == {"Authorization": "Bearer sp_at"}

    async def test_rest_fallback_to_download_aspx(
        self, transfer_service, sample_recordings, tmp_path
    ):
        """REST $value 401 falls back to download.aspx with token."""
        chunk = b"x" * 1024
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        dl_url = "https://tenant.sharepoint.com/sites/x/_layouts/15/download.aspx?UniqueId=abc"
        request = httpx.Request("GET", dl_url)
        rest_401 = httpx.HTTPStatusError(
            "Client error '401'",
            request=request,
            response=httpx.Response(401, request=request),
        )
        with (
            patch(
                "teamsleech.services.transfer.authenticate_sharepoint",
                AsyncMock(return_value="sp_at"),
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_client = self._mock_client(
                mock_cls,
                graph_resp=self._graph_redirect(location=dl_url),
            )
            mock_client.stream = MagicMock(
                side_effect=[
                    self._dl_resp(status_error=rest_401),
                    self._dl_resp(chunk),
                ]
            )
            size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        assert mock_client.stream.call_count == 2
        second_call = mock_client.stream.call_args_list[1]
        assert "download.aspx" in second_call.args[1]

    async def test_all_candidates_fail_reports_each(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        dl_url = "https://tenant.sharepoint.com/sites/x/_layouts/15/download.aspx?UniqueId=abc"
        request = httpx.Request("GET", dl_url)
        err401 = httpx.HTTPStatusError(
            "Client error '401'",
            request=request,
            response=httpx.Response(401, request=request),
        )
        with (
            patch(
                "teamsleech.services.transfer.authenticate_sharepoint",
                AsyncMock(return_value="sp_at"),
            ),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            self._mock_client(
                mock_cls, graph_resp=self._graph_redirect(location=dl_url)
            )
            mock_cls.return_value.__aenter__.return_value.stream = MagicMock(
                side_effect=lambda *a, **k: self._dl_resp(status_error=err401)
            )
            with pytest.raises(
                DownloadError, match=r"REST \$value \[401\].*download\.aspx"
            ):
                await transfer_service._download_recording(rec, dest)

    async def test_sharepoint_token_cached_per_host(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        with (
            patch(
                "teamsleech.services.transfer.authenticate_sharepoint",
                AsyncMock(return_value="sp_at"),
            ) as mock_sp,
            patch("httpx.AsyncClient") as mock_cls,
        ):
            self._mock_client(
                mock_cls,
                graph_resp=self._graph_redirect(),
                dl_resp=self._dl_resp(),
            )
            await transfer_service._download_recording(rec, dest)
            await transfer_service._download_recording(rec, dest)
        assert mock_sp.await_count == 1

    async def test_download_emits_dl_progress_and_done(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        events = []

        async def dl_cb(written, total, done=False):
            events.append((written, total, done))

        async def _two_chunks(**kw):
            yield b"x" * 1024
            yield b"x" * 1024

        with patch("httpx.AsyncClient") as mock_cls:
            self._mock_client(
                mock_cls, graph_resp=self._graph_redirect()
            )
            resp = AsyncMock()
            resp.__aenter__.return_value = resp
            resp.raise_for_status = MagicMock()
            resp.headers = {"content-length": "2048"}
            resp.aiter_bytes = MagicMock(side_effect=lambda **kw: _two_chunks())
            mock_cls.return_value.__aenter__.return_value.stream = MagicMock(
                return_value=resp
            )
            size = await transfer_service._download_recording(rec, dest, dl_cb)
        assert size == 2048
        assert events[-1] == (2048, 2048, True)
        assert events[0][0] == 1024

    async def test_cookies_tried_first_when_configured(
        self, transfer_service, sample_recordings, tmp_path, monkeypatch
    ):
        from teamsleech.core.config import settings
        monkeypatch.setattr(
            settings, "sp_cookies_json", '[{"name": "FedAuth", "value": "abc"}]'
        )
        chunk = b"x" * 1024
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = self._mock_client(
                mock_cls,
                graph_resp=self._graph_redirect(),
                dl_resp=self._dl_resp(chunk),
            )
            size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        first_call = mock_client.stream.call_args_list[0]
        assert "download.aspx" in first_call.args[1]
        assert first_call.kwargs["headers"] == {"Cookie": "FedAuth=abc"}

    async def test_stale_cookies_fall_through_to_anonymous(
        self, transfer_service, sample_recordings, tmp_path, monkeypatch
    ):
        from teamsleech.core.config import settings
        monkeypatch.setattr(
            settings, "sp_cookies_json", '[{"name": "FedAuth", "value": "stale"}]'
        )
        chunk = b"x" * 1024
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        dl_url = "https://tenant.sharepoint.com/sites/x/_layouts/15/download.aspx?UniqueId=abc"
        request = httpx.Request("GET", dl_url)
        err401 = httpx.HTTPStatusError(
            "Client error '401'",
            request=request,
            response=httpx.Response(401, request=request),
        )
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = self._mock_client(
                mock_cls, graph_resp=self._graph_redirect(location=dl_url)
            )
            mock_client.stream = MagicMock(
                side_effect=[
                    self._dl_resp(status_error=err401),
                    self._dl_resp(chunk),
                ]
            )
            size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        assert mock_client.stream.call_count == 2
        second_call = mock_client.stream.call_args_list[1]
        assert second_call.kwargs.get("headers") is None

    async def test_cookie_failure_hint_mentions_reexport(
        self, transfer_service, sample_recordings, tmp_path, monkeypatch
    ):
        from teamsleech.core.config import settings
        monkeypatch.setattr(
            settings, "sp_cookies_json", '[{"name": "FedAuth", "value": "stale"}]'
        )
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        dl_url = "https://tenant.sharepoint.com/sites/x/_layouts/15/download.aspx?UniqueId=abc"
        request = httpx.Request("GET", dl_url)
        err401 = httpx.HTTPStatusError(
            "Client error '401'",
            request=request,
            response=httpx.Response(401, request=request),
        )
        with patch("httpx.AsyncClient") as mock_cls:
            self._mock_client(
                mock_cls, graph_resp=self._graph_redirect(location=dl_url)
            )
            mock_cls.return_value.__aenter__.return_value.stream = MagicMock(
                side_effect=lambda *a, **k: self._dl_resp(status_error=err401)
            )
            with pytest.raises(DownloadError, match="re-export SP_COOKIES_JSON"):
                await transfer_service._download_recording(rec, dest)


class TestUploadToTelegram:
    async def test_upload_document(self, transfer_service, sample_recordings):
        sent_msg = AsyncMock()
        sent_msg.id = 42
        transfer_service._tg_send_document = AsyncMock(return_value=sent_msg)

        msg = await transfer_service._upload_to_telegram(
            "/tmp/notes.pdf", "notes.pdf", False, AsyncMock()
        )
        assert msg.id == 42
        transfer_service._tg_send_document.assert_awaited_once()

    async def test_upload_video(self, transfer_service, sample_recordings):
        sent_msg = AsyncMock()
        sent_msg.id = 43
        transfer_service._tg_send_video = AsyncMock(return_value=sent_msg)

        with (
            patch.object(transfer_service, "_probe_video", return_value=(60, 1920, 1080)),
            patch.object(transfer_service, "_extract_thumbnail", return_value="/tmp/thumb.jpg"),
        ):
            msg = await transfer_service._upload_to_telegram(
                "/tmp/lecture.mp4", "lecture.mp4", True, AsyncMock()
            )
        assert msg.id == 43

    async def test_upload_video_fallback_to_document(
        self, transfer_service, sample_recordings
    ):
        sent_msg = AsyncMock()
        sent_msg.id = 44
        from pyrogram.errors import BadRequest

        transfer_service._tg_send_video = AsyncMock(
            side_effect=BadRequest("VIDEO_FILE_INVALID")
        )
        transfer_service._tg_send_document = AsyncMock(return_value=sent_msg)

        with (
            patch.object(transfer_service, "_probe_video", return_value=(60, 1920, 1080)),
            patch.object(transfer_service, "_extract_thumbnail", return_value="/tmp/thumb.jpg"),
        ):
            msg = await transfer_service._upload_to_telegram(
                "/tmp/lecture.mp4", "lecture.mp4", True, AsyncMock()
            )
        assert msg.id == 44
        transfer_service._tg_send_document.assert_awaited_once()

    async def test_upload_non_video_bad_request_raises(
        self, transfer_service, sample_recordings
    ):
        from pyrogram.errors import BadRequest

        transfer_service._tg_send_document = AsyncMock(
            side_effect=BadRequest("FILE_TOO_BIG")
        )
        with pytest.raises(BadRequest):
            await transfer_service._upload_to_telegram(
                "/tmp/doc.pdf", "doc.pdf", False, AsyncMock()
            )

    async def test_upload_network_error(self, transfer_service, sample_recordings):
        transfer_service._tg_send_video = AsyncMock(
            side_effect=TimeoutError("Upload timed out")
        )
        with pytest.raises(TransferError, match="Upload failed"):
            await transfer_service._upload_to_telegram(
                "/tmp/lecture.mp4", "lecture.mp4", True, AsyncMock()
            )


class TestProgressReporting:
    async def test_report_progress_calls_callback(self, transfer_service):
        callback = AsyncMock()
        transfer_service._progress_last_time = 0.0
        transfer_service._progress_last_bytes = 0

        await transfer_service._report_progress(50, 100, 0, "test.mp4", callback)
        callback.assert_awaited()

    async def test_report_progress_skips_when_zero_total(self, transfer_service):
        callback = AsyncMock()
        await transfer_service._report_progress(0, 0, 0, "test.mp4", callback)
        callback.assert_not_called()

    async def test_report_progress_fires_at_100(self, transfer_service):
        callback = AsyncMock()
        transfer_service._progress_last_time = 0.0
        transfer_service._progress_last_bytes = 0

        await transfer_service._report_progress(100, 100, 0, "test.mp4", callback)
        callback.assert_awaited()

    async def test_report_progress_skips_non_multiple_of_5(self, transfer_service):
        callback = AsyncMock()
        transfer_service._progress_last_time = 0.0
        transfer_service._progress_last_bytes = 0

        await transfer_service._report_progress(3, 100, 0, "test.mp4", callback)
        callback.assert_not_called()


class TestUploadRecordings:
    async def test_upload_empty_list(self, transfer_service):
        results = await transfer_service.upload_recordings([])
        assert results == []

    async def test_upload_sends_progress_callbacks(self, transfer_service, sample_recordings):
        cb = AsyncMock()
        transfer_service._download_recording = AsyncMock(return_value=1024)
        transfer_service._upload_to_telegram = AsyncMock(return_value=AsyncMock(id=1))

        await transfer_service.upload_recordings(sample_recordings, cb)
        called_signals = [c.args[0] for c in cb.await_args_list]
        assert "start" in called_signals
        assert "all_done" in called_signals

    async def test_upload_producer_download_error(
        self, transfer_service, sample_recordings
    ):
        cb = AsyncMock()
        transfer_service._download_recording = AsyncMock(
            side_effect=DownloadError("Disk full")
        )

        results = await transfer_service.upload_recordings(sample_recordings, cb)
        assert len(results) == 2
        assert not results[0]["success"]
        assert "Disk full" in results[0]["error"]

    async def test_upload_consumer_upload_error(
        self, transfer_service, sample_recordings
    ):
        cb = AsyncMock()
        transfer_service._download_recording = AsyncMock(return_value=1024)
        transfer_service._upload_to_telegram = AsyncMock(
            side_effect=TelegramUploadError("Upload quota exceeded")
        )

        results = await transfer_service.upload_recordings(sample_recordings, cb)
        assert len(results) == 2
        # One recording should succeed the download, fail the upload
        # The other should also pass through
        assert any(not r["success"] for r in results)

    async def test_upload_cleans_up_temp_files(
        self, transfer_service, sample_recordings
    ):
        with patch("os.unlink") as mock_unlink:
            transfer_service._download_recording = AsyncMock(return_value=1024)
            transfer_service._upload_to_telegram = AsyncMock(
                return_value=AsyncMock(id=1)
            )

            await transfer_service.upload_recordings(sample_recordings)
            # Each recording gets a temp file cleaned up
            assert mock_unlink.call_count >= len(sample_recordings)
