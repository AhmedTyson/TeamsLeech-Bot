import logging
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
            name="lecture1.mp4",
            size_mb=100.0,
            created="2024-01-15",
            time="10:00",
            duration_ms=1_800_000,
            drive_id="d1",
            item_id="i1",
            team_name="CS-A",
            subject_name="Math",
            is_video=True,
        ),
        Recording(
            name="notes.pdf",
            size_mb=5.0,
            created="2024-01-15",
            time="10:00",
            duration_ms=0,
            drive_id="d1",
            item_id="i2",
            team_name="CS-A",
            subject_name="Math",
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
    def _mock_stream_response(self, transfer_service, resp):
        stream_cm = AsyncMock()
        stream_cm.__aenter__.return_value = resp
        stream_cm.__aexit__.return_value = None
        transfer_service.graph.client.stream = MagicMock(return_value=stream_cm)
        transfer_service.graph.get = AsyncMock(return_value={})
        return stream_cm

    async def test_download_success(self, transfer_service, sample_recordings, tmp_path):
        chunk = b"x" * 1024
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        resp = AsyncMock()
        resp.__aenter__.return_value = resp
        resp.raise_for_status = MagicMock()
        resp.headers = {}

        async def _iter(**kw):
            yield chunk

        resp.aiter_bytes = MagicMock(side_effect=lambda **kw: _iter())
        self._mock_stream_response(transfer_service, resp)

        size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)

    async def test_download_network_error(self, transfer_service, sample_recordings, tmp_path):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        transfer_service.graph.client.stream = MagicMock(
            side_effect=httpx.RequestError("Connection refused")
        )
        transfer_service.graph.get = AsyncMock(return_value={})

        with pytest.raises(DownloadError, match="Connection refused"):
            await transfer_service._download_recording(rec, dest)

    async def test_download_stream_error_midway(
        self, transfer_service, sample_recordings, tmp_path
    ):
        """Simulate stream failing mid-download after some chunks."""
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        resp = AsyncMock()
        resp.__aenter__.return_value = resp
        resp.raise_for_status = MagicMock()
        resp.headers = {}

        async def fail_after_one(**kw):
            yield b"x" * 1024
            msg = "Stream interrupted"
            raise httpx.RequestError(msg)

        resp.aiter_bytes = MagicMock(side_effect=fail_after_one)
        self._mock_stream_response(transfer_service, resp)

        with pytest.raises(DownloadError, match="Stream interrupted"):
            await transfer_service._download_recording(rec, dest)

    async def test_download_http_error_retried_then_succeeds(
        self, transfer_service, sample_recordings, tmp_path
    ):
        """429 on first attempt retried via DownloadError wrap, then succeeds."""
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        req = httpx.Request("GET", "https://graph.microsoft.com/v1.0/drives/d1/items/i1/content")
        err = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=req,
            response=httpx.Response(429, request=req),
        )

        chunk = b"y" * 512
        resp = AsyncMock()
        resp.__aenter__.return_value = resp
        resp.raise_for_status = MagicMock()
        resp.headers = {}

        async def _iter(**kw):
            yield chunk

        resp.aiter_bytes = MagicMock(side_effect=lambda **kw: _iter())
        stream_cm = AsyncMock()
        stream_cm.__aenter__.return_value = resp
        stream_cm.__aexit__.return_value = None
        transfer_service.graph.client.stream = MagicMock(side_effect=[err, stream_cm])
        transfer_service.graph.get = AsyncMock(return_value={})

        size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        assert transfer_service.graph.client.stream.call_count == 2

    async def test_download_rejects_oversize_content_length(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        resp = AsyncMock()
        resp.__aenter__.return_value = resp
        resp.raise_for_status = MagicMock()
        resp.headers = {"content-length": str(3 * 1024 * 1024 * 1024)}
        self._mock_stream_response(transfer_service, resp)

        with pytest.raises(DownloadError, match="exceeds Telegram"):
            await transfer_service._download_recording(rec, dest)

    async def test_download_prefers_presigned_url_without_auth(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        chunk = b"x" * 128
        resp = AsyncMock()
        resp.__aenter__.return_value = resp
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.headers = {}

        async def _iter(**kw):
            yield chunk

        resp.aiter_bytes = MagicMock(side_effect=lambda **kw: _iter())
        stream_cm = AsyncMock()
        stream_cm.__aenter__.return_value = resp
        stream_cm.__aexit__.return_value = None
        seen: list[dict] = []

        def _stream(method, url, **kwargs):
            seen.append({"url": url, "headers": dict(kwargs.get("headers", {}))})
            return stream_cm

        transfer_service.graph.client.stream = MagicMock(side_effect=_stream)
        transfer_service.graph.get = AsyncMock(
            return_value={"@microsoft.graph.downloadUrl": "https://cdn.example.com/f?token=abc"}
        )

        size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        assert seen[0]["url"] == "https://cdn.example.com/f?token=abc"
        assert "Authorization" not in seen[0]["headers"]

    async def test_download_unauthorized_fails_fast_without_retry(
        self, transfer_service, sample_recordings, tmp_path
    ):
        from teamsleech.services.transfer import DownloadAuthError

        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        req = httpx.Request("GET", "https://sharepoint.example.com/download.aspx")
        resp = AsyncMock()
        resp.__aenter__.return_value = resp
        resp.status_code = 401
        resp.headers = {}
        resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized", request=req, response=httpx.Response(401, request=req)
            )
        )
        stream_cm = AsyncMock()
        stream_cm.__aenter__.return_value = resp
        stream_cm.__aexit__.return_value = None
        transfer_service.graph.client.stream = MagicMock(return_value=stream_cm)
        transfer_service.graph.get = AsyncMock(return_value={})

        with pytest.raises(DownloadAuthError, match="401"):
            await transfer_service._download_recording(rec, dest)
        assert transfer_service.graph.client.stream.call_count == 1

    async def test_sharepoint_401_twice_still_fails_fast(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        target = "https://tenant.sharepoint.com/sites/X/download.aspx?UniqueId=1"
        req = httpx.Request("GET", target)
        denied = AsyncMock()
        denied.__aenter__.return_value = denied
        denied.status_code = 401
        denied.headers = {}
        denied.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized", request=req, response=httpx.Response(401, request=req)
            )
        )

        def _cm(resp):
            cm = AsyncMock()
            cm.__aenter__.return_value = resp
            cm.__aexit__.return_value = None
            return cm

        transfer_service.graph.client.stream = MagicMock(return_value=_cm(denied))
        transfer_service.graph.get = AsyncMock(
            return_value={"@microsoft.graph.downloadUrl": target}
        )

        from teamsleech.services.auth import TokenExchangeError

        with (
            patch(
                "teamsleech.services.transfer.exchange_sharepoint_token",
                new=AsyncMock(side_effect=TokenExchangeError("consent required")),
            ),
            patch(
                "teamsleech.services.transfer.exchange_sharepoint_token_v1",
                new=AsyncMock(side_effect=TokenExchangeError("consent required")),
            ),
        ):
            with pytest.raises(DownloadError, match="401"):
                await transfer_service._download_recording(rec, dest)
        assert transfer_service.graph.client.stream.call_count == 1

    async def test_sharepoint_401_uses_sp_token_and_rotates(
        self, transfer_service, sample_recordings, tmp_path
    ):
        from teamsleech.core.config import settings

        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        target = "https://tenant.sharepoint.com/sites/X/download.aspx?UniqueId=1"
        req = httpx.Request("GET", target)
        denied = AsyncMock()
        denied.__aenter__.return_value = denied
        denied.status_code = 401
        denied.headers = {}
        denied.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized", request=req, response=httpx.Response(401, request=req)
            )
        )
        chunk = b"z" * 64
        granted = AsyncMock()
        granted.__aenter__.return_value = granted
        granted.status_code = 200
        granted.headers = {}
        granted.raise_for_status = MagicMock()

        async def _iter(**kw):
            yield chunk

        granted.aiter_bytes = MagicMock(side_effect=lambda **kw: _iter())

        def _cm(resp):
            cm = AsyncMock()
            cm.__aenter__.return_value = resp
            cm.__aexit__.return_value = None
            return cm

        seen: list[dict] = []

        def _stream(method, url, **kwargs):
            seen.append(dict(kwargs.get("headers", {})))
            return _cm(denied) if len(seen) == 1 else _cm(granted)

        transfer_service.graph.client.stream = MagicMock(side_effect=_stream)
        transfer_service.graph.get = AsyncMock(
            return_value={"@microsoft.graph.downloadUrl": target}
        )
        with (
            patch(
                "teamsleech.services.transfer.exchange_sharepoint_token",
                new=AsyncMock(return_value=("sp_access", "rt_new")),
            ),
            patch(
                "teamsleech.services.transfer.rotate_github_secret",
                new=AsyncMock(),
            ) as rotate,
        ):
            size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        assert "Authorization" not in seen[0]
        assert seen[1]["Authorization"] == "Bearer sp_access"
        assert settings.teams_refresh_token == "rt_new"
        rotate.assert_awaited_once()

    async def test_sharepoint_api_download_succeeds_after_token_retries(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        target = "https://tenant.sharepoint.com/sites/X/download.aspx?UniqueId=1"
        req = httpx.Request("GET", target)
        denied = AsyncMock()
        denied.__aenter__.return_value = denied
        denied.status_code = 401
        denied.headers = {}
        denied.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized", request=req, response=httpx.Response(401, request=req)
            )
        )
        chunk = b"q" * 32
        granted = AsyncMock()
        granted.__aenter__.return_value = granted
        granted.status_code = 200
        granted.headers = {}
        granted.raise_for_status = MagicMock()

        async def _iter(**kw):
            yield chunk

        granted.aiter_bytes = MagicMock(side_effect=lambda **kw: _iter())

        def _cm(resp):
            cm = AsyncMock()
            cm.__aenter__.return_value = resp
            cm.__aexit__.return_value = None
            return cm

        seen: list[dict] = []

        def _stream(method, url, **kwargs):
            seen.append({"url": url, "headers": dict(kwargs.get("headers", {}))})
            if len(seen) < 4:
                return _cm(denied)
            return _cm(granted)

        transfer_service.graph.client.stream = MagicMock(side_effect=_stream)
        transfer_service.graph.get = AsyncMock(
            return_value={"@microsoft.graph.downloadUrl": target}
        )
        with (
            patch(
                "teamsleech.services.transfer.exchange_sharepoint_token",
                new=AsyncMock(return_value=("tok_a", "rt_a")),
            ),
            patch(
                "teamsleech.services.transfer.exchange_sharepoint_token_v1",
                new=AsyncMock(return_value=("tok_b", "rt_b")),
            ),
            patch(
                "teamsleech.services.transfer.rotate_github_secret",
                new=AsyncMock(),
            ),
        ):
            size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        assert len(seen) == 4
        assert "GetFileById('1')" in seen[3]["url"]
        assert seen[3]["headers"]["Authorization"] == "Bearer tok_b"

    async def test_bare_download_url_retried_after_ladder(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        base = "https://tenant.sharepoint.com/sites/X/_layouts/15/download.aspx"
        target = f"{base}?UniqueId=1&Translate=false&ApiVersion=2.0"
        bare = f"{base}?UniqueId=1"
        req = httpx.Request("GET", target)
        denied = AsyncMock()
        denied.__aenter__.return_value = denied
        denied.status_code = 401
        denied.headers = {}
        denied.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized", request=req, response=httpx.Response(401, request=req)
            )
        )
        denied.aread = AsyncMock(return_value=b"err")
        chunk = b"q" * 32
        granted = AsyncMock()
        granted.__aenter__.return_value = granted
        granted.status_code = 200
        granted.headers = {}
        granted.raise_for_status = MagicMock()

        async def _iter(**kw):
            yield chunk

        granted.aiter_bytes = MagicMock(side_effect=lambda **kw: _iter())

        def _cm(resp):
            cm = AsyncMock()
            cm.__aenter__.return_value = resp
            cm.__aexit__.return_value = None
            return cm

        seen: list[dict] = []

        def _stream(method, url, **kwargs):
            seen.append({"url": url, "headers": dict(kwargs.get("headers", {}))})
            return _cm(granted) if url == bare else _cm(denied)

        transfer_service.graph.client.stream = MagicMock(side_effect=_stream)
        transfer_service.graph.get = AsyncMock(
            return_value={"@microsoft.graph.downloadUrl": target}
        )
        with (
            patch(
                "teamsleech.services.transfer.exchange_sharepoint_token",
                new=AsyncMock(return_value=("tok_a", "rt_a")),
            ),
            patch(
                "teamsleech.services.transfer.exchange_sharepoint_token_v1",
                new=AsyncMock(return_value=("tok_b", "rt_b")),
            ),
            patch(
                "teamsleech.services.transfer.rotate_github_secret",
                new=AsyncMock(),
            ),
        ):
            size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        assert seen[-1]["url"] == bare
        assert seen[-1]["headers"]["Authorization"] == "Bearer tok_b"

    async def test_bare_download_target_edge_cases(self):
        from teamsleech.services.transfer import TransferService

        fn = TransferService._bare_download_target
        assert fn("https://cdn.example.com/f?token=abc") is None
        assert fn("https://t.sharepoint.com/x/download.aspx?UniqueId=1") is None
        assert fn("https://t.sharepoint.com/x/download.aspx?other=2") is None
        got = fn("https://t.sharepoint.com/x/download.aspx?UniqueId=1&Translate=false")
        assert got == "https://t.sharepoint.com/x/download.aspx?UniqueId=1"

    async def test_sharepoint_api_failure_fails_fast(
        self, transfer_service, sample_recordings, tmp_path
    ):
        from teamsleech.services.transfer import DownloadAuthError

        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        target = "https://tenant.sharepoint.com/sites/X/download.aspx?UniqueId=1"
        req = httpx.Request("GET", target)
        denied = AsyncMock()
        denied.__aenter__.return_value = denied
        denied.status_code = 401
        denied.headers = {}
        denied.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized", request=req, response=httpx.Response(401, request=req)
            )
        )
        missing = AsyncMock()
        missing.__aenter__.return_value = missing
        missing.status_code = 404
        missing.headers = {}
        missing.raise_for_status = MagicMock()

        def _cm(resp):
            cm = AsyncMock()
            cm.__aenter__.return_value = resp
            cm.__aexit__.return_value = None
            return cm

        calls = {"n": 0}

        def _stream(method, url, **kwargs):
            calls["n"] += 1
            if calls["n"] < 4:
                return _cm(denied)
            return _cm(missing)

        transfer_service.graph.client.stream = MagicMock(side_effect=_stream)
        transfer_service.graph.get = AsyncMock(
            return_value={"@microsoft.graph.downloadUrl": target}
        )
        with (
            patch(
                "teamsleech.services.transfer.exchange_sharepoint_token",
                new=AsyncMock(return_value=("tok_a", "rt_a")),
            ),
            patch(
                "teamsleech.services.transfer.exchange_sharepoint_token_v1",
                new=AsyncMock(return_value=("tok_b", "rt_b")),
            ),
            patch(
                "teamsleech.services.transfer.rotate_github_secret",
                new=AsyncMock(),
            ),
        ):
            with pytest.raises(DownloadAuthError, match="401"):
                await transfer_service._download_recording(rec, dest)
        assert calls["n"] == 4

    async def test_sharepoint_api_malformed_target_returns_none(self, transfer_service):
        from teamsleech.models.domain import Recording

        recording = Recording(
            name="x.mp4",
            size_mb=1.0,
            created="2024-01-01",
            time="10:00",
            duration_ms=0,
            drive_id="d",
            item_id="i",
            team_name="t",
            subject_name="s",
            is_video=True,
        )
        result = await transfer_service._download_via_sharepoint_api(
            recording, "https://tenant.sharepoint.com/sites/X/other", "tok", "/tmp/x"
        )
        assert result is None

    async def test_plain_metadata_fallback_for_download_url(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        chunk = b"q" * 32
        resp = AsyncMock()
        resp.__aenter__.return_value = resp
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.headers = {}

        async def _iter(**kw):
            yield chunk

        resp.aiter_bytes = MagicMock(side_effect=lambda **kw: _iter())
        stream_cm = AsyncMock()
        stream_cm.__aenter__.return_value = resp
        stream_cm.__aexit__.return_value = None
        seen: list[dict] = []

        def _stream(method, url, **kwargs):
            seen.append({"url": url, "headers": dict(kwargs.get("headers", {}))})
            return stream_cm

        transfer_service.graph.client.stream = MagicMock(side_effect=_stream)
        transfer_service.graph.get = AsyncMock(
            side_effect=[
                {"id": "i1"},
                {"@microsoft.graph.downloadUrl": "https://cdn.example.com/f"},
            ]
        )
        size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        assert seen[0]["url"] == "https://cdn.example.com/f"
        assert "Authorization" not in seen[0]["headers"]

    async def test_401_body_logged_for_diagnosis(
        self, transfer_service, sample_recordings, tmp_path, caplog
    ):
        from teamsleech.services.transfer import DownloadAuthError

        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        target = "https://cdn.example.com/f"
        req = httpx.Request("GET", target)
        denied = AsyncMock()
        denied.__aenter__.return_value = denied
        denied.status_code = 401
        denied.headers = {}
        denied.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized", request=req, response=httpx.Response(401, request=req)
            )
        )
        denied.aread = AsyncMock(return_value=b"<error>denied-by-policy</error>")

        def _cm(resp):
            cm = AsyncMock()
            cm.__aenter__.return_value = resp
            cm.__aexit__.return_value = None
            return cm

        transfer_service.graph.client.stream = MagicMock(return_value=_cm(denied))
        transfer_service.graph.get = AsyncMock(return_value={})

        with caplog.at_level(logging.WARNING, logger="transfer"):
            with pytest.raises(DownloadAuthError, match="401"):
                await transfer_service._download_recording(rec, dest)
        assert "denied-by-policy" in caplog.text

    async def test_download_redirect_strips_auth_cross_host(
        self, transfer_service, sample_recordings, tmp_path
    ):
        rec = sample_recordings[0]
        dest = str(tmp_path / "t.mp4")
        chunk = b"z" * 64

        redirect = AsyncMock()
        redirect.__aenter__.return_value = redirect
        redirect.status_code = 302
        redirect.headers = {"location": "https://cdn.example.com/file.mp4"}

        final = AsyncMock()
        final.__aenter__.return_value = final
        final.status_code = 200
        final.raise_for_status = MagicMock()
        final.headers = {}

        async def _iter(**kw):
            yield chunk

        final.aiter_bytes = MagicMock(side_effect=lambda **kw: _iter())

        def _cm(resp):
            cm = AsyncMock()
            cm.__aenter__.return_value = resp
            cm.__aexit__.return_value = None
            return cm

        seen: list[dict] = []

        def _stream(method, url, **kwargs):
            seen.append(dict(kwargs.get("headers", {})))
            return _cm(redirect) if len(seen) == 1 else _cm(final)

        transfer_service.graph.client.stream = MagicMock(side_effect=_stream)
        transfer_service.graph.get = AsyncMock(return_value={})

        size = await transfer_service._download_recording(rec, dest)
        assert size == len(chunk)
        assert seen[0]["Authorization"].startswith("Bearer ")
        assert "Authorization" not in seen[1]


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

    async def test_upload_truncates_long_caption(self, transfer_service):
        sent_msg = AsyncMock()
        sent_msg.id = 45
        transfer_service._tg_send_document = AsyncMock(return_value=sent_msg)

        long_name = "n" * 1500 + ".pdf"
        await transfer_service._upload_to_telegram("/tmp/doc.pdf", long_name, False, AsyncMock())
        caption = transfer_service._tg_send_document.await_args.args[3]
        assert len(caption) <= 1024

    async def test_upload_rejects_over_bot_limit_without_session(self, transfer_service):
        from teamsleech.services.transfer import TelegramUploadError

        with patch("os.path.getsize", return_value=200 * 1024 * 1024):
            with pytest.raises(TelegramUploadError, match="TELEGRAM_SESSION_STRING"):
                await transfer_service._upload_to_telegram(
                    "/tmp/big.mp4", "big.mp4", False, AsyncMock()
                )

    async def test_upload_uses_session_client_when_configured(
        self, graph_client, mock_pyrogram_client
    ):
        from teamsleech.services.transfer import TransferService

        user_client = AsyncMock()
        svc = TransferService(graph_client, AsyncMock(), mock_pyrogram_client, 67890, user_client)
        sent_msg = AsyncMock()
        sent_msg.id = 46
        user_client.send_document = AsyncMock(return_value=sent_msg)

        with patch("os.path.getsize", return_value=500 * 1024 * 1024):
            msg = await svc._upload_to_telegram("/tmp/big.pdf", "big.pdf", False, AsyncMock())
        assert msg.id == 46
        user_client.send_document.assert_awaited_once()

    async def test_upload_video_fallback_to_document(self, transfer_service, sample_recordings):
        sent_msg = AsyncMock()
        sent_msg.id = 44
        from pyrogram.errors import BadRequest

        transfer_service._tg_send_video = AsyncMock(side_effect=BadRequest("VIDEO_FILE_INVALID"))
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

    async def test_upload_non_video_bad_request_raises(self, transfer_service, sample_recordings):
        from pyrogram.errors import BadRequest

        transfer_service._tg_send_document = AsyncMock(side_effect=BadRequest("FILE_TOO_BIG"))
        with pytest.raises(BadRequest):
            await transfer_service._upload_to_telegram(
                "/tmp/doc.pdf", "doc.pdf", False, AsyncMock()
            )

    async def test_upload_network_error(self, transfer_service, sample_recordings):
        transfer_service._tg_send_video = AsyncMock(side_effect=TimeoutError("Upload timed out"))
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

    async def test_upload_producer_download_error(self, transfer_service, sample_recordings):
        cb = AsyncMock()
        transfer_service._download_recording = AsyncMock(side_effect=DownloadError("Disk full"))

        results = await transfer_service.upload_recordings(sample_recordings, cb)
        assert len(results) == 2
        assert not results[0]["success"]
        assert "Disk full" in results[0]["error"]

    async def test_upload_consumer_upload_error(self, transfer_service, sample_recordings):
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

    async def test_upload_producer_unexpected_error_no_hang(
        self, transfer_service, sample_recordings
    ):
        """Unexpected producer error records failure and still ends consumer."""
        import asyncio

        cb = AsyncMock()
        transfer_service._download_recording = AsyncMock(side_effect=RuntimeError("boom"))

        results = await asyncio.wait_for(
            transfer_service.upload_recordings(sample_recordings, cb), timeout=15
        )
        assert len(results) == 2
        assert all(not r["success"] for r in results)
        assert all("boom" in r["error"] for r in results)

    async def test_upload_cleans_up_temp_files(self, transfer_service, sample_recordings):
        with patch("os.unlink") as mock_unlink:
            transfer_service._download_recording = AsyncMock(return_value=1024)
            transfer_service._upload_to_telegram = AsyncMock(return_value=AsyncMock(id=1))

            await transfer_service.upload_recordings(sample_recordings)
            # Each recording gets a temp file cleaned up
            assert mock_unlink.call_count >= len(sample_recordings)
