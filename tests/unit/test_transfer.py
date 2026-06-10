from unittest.mock import AsyncMock, patch, MagicMock, call

import httpx
import pytest

from teamsleech.services.transfer import (
    TransferService,
    DownloadError,
    TelegramUploadError,
    TransferError,
)
from teamsleech.models.domain import Recording


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
    async def test_download_success(self, transfer_service, sample_recordings):
        chunk = b"x" * 1024
        rec = sample_recordings[0]
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            resp = AsyncMock()
            resp.__aenter__.return_value = resp

            async def _iter():
                yield chunk
            resp.aiter_bytes = MagicMock(return_value=_iter())

            mock_client.stream.return_value = resp

            size = await transfer_service._download_recording(rec, "/tmp/t.mp4")
        assert size == len(chunk)

    async def test_download_network_error(self, transfer_service, sample_recordings):
        rec = sample_recordings[0]
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.stream.side_effect = __import__(
                "httpx"
            ).RequestError("Connection refused")

            with pytest.raises(DownloadError, match="Connection refused"):
                await transfer_service._download_recording(rec, "/tmp/t.mp4")

    async def test_download_stream_error_midway(self, transfer_service, sample_recordings):
        """Simulate stream failing mid-download after some chunks."""
        rec = sample_recordings[0]
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            resp = AsyncMock()
            resp.__aenter__.return_value = resp

            async def fail_after_one():
                yield b"x" * 1024
                raise httpx.RequestError("Stream interrupted")

            resp.aiter_bytes = MagicMock(side_effect=lambda **kw: fail_after_one())
            mock_client.stream.return_value = resp

            with pytest.raises(DownloadError, match="Stream interrupted"):
                await transfer_service._download_recording(rec, "/tmp/t.mp4")


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
