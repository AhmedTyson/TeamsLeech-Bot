"""Unit tests for the remote-browser self-login service."""

import sys
import types
from unittest.mock import patch

import pytest

from teamsleech.services import browser_login as bl


def test_generate_password_short_and_random():
    p1, p2 = bl.generate_password(), bl.generate_password()
    assert 0 < len(p1) <= 8  # VNC truncates at 8 chars
    assert p1 != p2


def test_parse_tunnel_url_found_in_noise():
    text = (
        "2026-11-28T00:00:00Z INF Thank you for trying Cloudflare Tunnel.\n"
        "2026-11-28T00:00:01Z INF "
        "https://funny-words-here-123.trycloudflare.com created\n"
    )
    assert bl.parse_tunnel_url(text) == "https://funny-words-here-123.trycloudflare.com"


def test_parse_tunnel_url_absent():
    assert bl.parse_tunnel_url("no url here") is None
    assert bl.parse_tunnel_url("https://example.com/not-a-tunnel") is None


def test_parse_tunnel_url_localhost_run():
    text = (
        "Welcome to localhost.run!\n"
        "abc123.lhr.life tunneled with tls termination,"
        " https://abc123.lhr.life\r\n"
    )
    assert bl.parse_tunnel_url(text, bl.LHR_URL_RE) == "https://abc123.lhr.life"
    assert bl.parse_tunnel_url("no url here", bl.LHR_URL_RE) is None


def test_filter_session_cookies_keeps_auth_domains():
    cookies = [
        {"name": "FedAuth", "value": "x", "domain": "tenant.sharepoint.com"},
        {"name": "rtFa", "value": "y", "domain": "tenant.sharepoint.com"},
        {"name": "ESTSAUTH", "value": "z", "domain": ".login.microsoftonline.com"},
        {"name": "tracking", "value": "t", "domain": ".ads.example.com"},
    ]
    kept, found = bl.filter_session_cookies(cookies)
    assert len(kept) == 3
    assert "FedAuth" in found
    assert "rtFa" in found
    # ESTSAUTH is a login-flow cookie, not a SharePoint session marker.
    assert "ESTSAUTH" not in found


def test_login_page_cookies_are_not_a_session():
    """Regression: the login PAGE sets RpsContextCookie before any password
    is typed — it must never count as a saved session."""
    cookies = [
        {"name": "RpsContextCookie", "value": "r", "domain": ".login.microsoftonline.com"},
        {"name": "ESTSAUTH", "value": "e", "domain": ".login.microsoftonline.com"},
        {"name": "ESTSAUTHPERSISTENT", "value": "p", "domain": ".login.microsoftonline.com"},
        {"name": "buid", "value": "b", "domain": ".login.microsoftonline.com"},
    ]
    kept, found = bl.filter_session_cookies(cookies)
    assert len(kept) == 4
    assert found == []


def test_marker_on_wrong_domain_does_not_count():
    cookies = [
        {"name": "FedAuth", "value": "x", "domain": ".login.microsoftonline.com"},
    ]
    _, found = bl.filter_session_cookies(cookies)
    assert found == []


def test_filter_session_cookies_no_markers():
    cookies = [{"name": "anon", "value": "1", "domain": ".sharepoint.com"}]
    kept, found = bl.filter_session_cookies(cookies)
    assert len(kept) == 1
    assert found == []


def test_export_cookie_list_shape():
    kept = [
        {"name": "FedAuth", "value": "x", "domain": "d", "path": "/",
         "secure": True, "expires": 123},
        {"name": "", "value": "skip", "domain": "d"},
    ]
    exported = bl.export_cookie_list(kept)
    assert exported == [
        {"name": "FedAuth", "value": "x", "domain": "d", "path": "/"}
    ]


class FakeContext:
    def __init__(self, snapshots):
        self._snapshots = list(snapshots)
        self.closed = False

    async def cookies(self):
        if len(self._snapshots) > 1:
            return self._snapshots.pop(0)
        return self._snapshots[0]

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_wait_for_session_cookies_success():
    ctx = FakeContext([
        [],
        [{"name": "FedAuth", "value": "x", "domain": "tenant.sharepoint.com"}],
    ])
    kept, found = await bl.wait_for_session_cookies(ctx, 5, poll_seconds=0.01)
    assert found == ["FedAuth"]
    assert kept[0]["name"] == "FedAuth"


@pytest.mark.asyncio
async def test_wait_for_session_cookies_timeout():
    ctx = FakeContext([[]])
    with pytest.raises(TimeoutError):
        await bl.wait_for_session_cookies(ctx, 0.05, poll_seconds=0.01)


@pytest.mark.asyncio
async def test_wait_for_session_cookies_tolerates_poll_errors():
    class Flaky:
        def __init__(self):
            self.calls = 0

        async def cookies(self):
            self.calls += 1
            if self.calls < 2:
                raise RuntimeError("target detached")
            return [{"name": "rtFa", "value": "y", "domain": ".sharepoint.com"}]

    kept, found = await bl.wait_for_session_cookies(Flaky(), 5, poll_seconds=0.01)
    assert "rtFa" in found


class FakeProc:
    """Stands in for Xvfb/x11vnc/websockify/cloudflared."""

    def __init__(self, lines=None):
        self.stdout = FakeStream(lines or [])
        self.terminated = False
        self.returncode = None

    def terminate(self):
        self.terminated = True

    async def wait(self):
        return 0


class FakeStream:
    def __init__(self, lines):
        self._lines = [line.encode() for line in lines]

    async def readline(self):
        if self._lines:
            return self._lines.pop(0)
        return b""


def _fake_spawn(tunnel_lines):
    async def spawn(*args, pipe_output=False):
        if args[0] == "cloudflared":
            return FakeProc(tunnel_lines)
        return FakeProc()

    return spawn


def _fake_playwright(context):
    """Insert a fake playwright.async_api module for the lazy import."""
    pw_instance = types.SimpleNamespace(
        chromium=types.SimpleNamespace(),
        stopped=False,
    )

    async def launch_persistent_context(*args, **kwargs):
        return context

    pw_instance.chromium.launch_persistent_context = launch_persistent_context

    async def stop():
        pw_instance.stopped = True

    pw_instance.stop = stop

    class FakeManager:
        async def start(self):
            return pw_instance

    def async_playwright():
        return FakeManager()

    module = types.ModuleType("playwright.async_api")
    module.async_playwright = async_playwright
    return module, pw_instance


@pytest.mark.asyncio
async def test_run_browser_login_saves_cookies_and_dispatches():
    context = FakeContext([
        [{"name": "FedAuth", "value": "x", "domain": "tenant.sharepoint.com"}],
    ])
    context.pages = [types.SimpleNamespace(goto=_async_noop())]
    pw_module, pw_instance = _fake_playwright(context)
    notes = []
    saved = {}
    dispatched = []

    async def notify(text):
        notes.append(text)

    async def rotate(name, value):
        saved[name] = value

    async def dispatch(wf):
        dispatched.append(wf)

    async def healthy_local(**kwargs):
        return True

    async def healthy_public(*args, **kwargs):
        return 200

    with (
        patch.object(bl, "_spawn", _fake_spawn(["https://abc-def.trycloudflare.com\n"])),
        patch.object(bl, "wait_for_local_origin", healthy_local),
        patch.object(bl, "wait_for_public_tunnel", healthy_public),
        patch.object(bl, "rotate_github_secret", rotate),
        patch.object(bl, "dispatch_workflow", dispatch),
        patch.dict(sys.modules, {"playwright.async_api": pw_module}),
    ):
        ok = await bl.run_browser_login(
            notify=notify, timeout_minutes=1, site_url="https://tenant.sharepoint.com/"
        )

    assert ok is True
    assert bl.COOKIE_SECRET in saved
    assert "FedAuth" in saved[bl.COOKIE_SECRET]
    assert dispatched == [bl.BOT_RUNNER_WORKFLOW]
    assert any("Browser login ready" in n for n in notes)
    assert any("Session saved" in n for n in notes)
    assert context.closed is True
    assert pw_instance.stopped is True


@pytest.mark.asyncio
async def test_run_browser_login_prefers_localhost_run():
    """localhost.run answers first -> cloudflared is never spawned."""
    context = FakeContext([
        [{"name": "FedAuth", "value": "x", "domain": "tenant.sharepoint.com"}],
    ])
    context.pages = [types.SimpleNamespace(goto=_async_noop())]
    pw_module, _ = _fake_playwright(context)
    spawned = []
    notes = []
    saved = {}

    async def spawn(*args, pipe_output=False):
        spawned.append(args[0])
        if args[0] == "ssh":
            return FakeProc([
                "abc123.lhr.life tunneled with tls termination,"
                " https://abc123.lhr.life\n"
            ])
        return FakeProc()

    async def notify(text):
        notes.append(text)

    async def rotate(name, value):
        saved[name] = value

    async def dispatch(wf):
        pass

    async def healthy_local(**kwargs):
        return True

    async def healthy_public(*args, **kwargs):
        return 200

    with (
        patch.object(bl, "_spawn", spawn),
        patch.object(bl, "wait_for_local_origin", healthy_local),
        patch.object(bl, "wait_for_public_tunnel", healthy_public),
        patch.object(bl, "rotate_github_secret", rotate),
        patch.object(bl, "dispatch_workflow", dispatch),
        patch.dict(sys.modules, {"playwright.async_api": pw_module}),
    ):
        ok = await bl.run_browser_login(
            notify=notify, timeout_minutes=1, site_url="https://tenant.sharepoint.com/"
        )

    assert ok is True
    assert "ssh" in spawned
    assert "cloudflared" not in spawned
    assert any("https://abc123.lhr.life" in n for n in notes)


@pytest.mark.asyncio
async def test_run_browser_login_tunnel_failure():
    context = FakeContext([[]])
    context.pages = [types.SimpleNamespace(goto=_async_noop())]
    pw_module, _ = _fake_playwright(context)
    notes = []

    async def notify(text):
        notes.append(text)

    with (
        patch.object(bl, "_spawn", _fake_spawn(["no url ever\n"])),
        patch.object(bl, "_wait_tunnel_url", _none()),
        patch.dict(sys.modules, {"playwright.async_api": pw_module}),
    ):
        ok = await bl.run_browser_login(notify=notify, timeout_minutes=1)

    assert ok is False
    assert any("could not start" in n for n in notes)


@pytest.mark.asyncio
async def test_run_browser_login_timeout_notifies():
    context = FakeContext([[]])
    context.pages = [types.SimpleNamespace(goto=_async_noop())]
    pw_module, _ = _fake_playwright(context)
    notes = []

    async def notify(text):
        notes.append(text)

    async def _timeout_wait(context, timeout_seconds, poll_seconds=0):
        raise TimeoutError("no cookies")

    async def healthy_local(**kwargs):
        return True

    async def healthy_public(*args, **kwargs):
        return 200

    with (
        patch.object(bl, "_spawn", _fake_spawn(["https://x-y.trycloudflare.com\n"])),
        patch.object(bl, "wait_for_local_origin", healthy_local),
        patch.object(bl, "wait_for_public_tunnel", healthy_public),
        patch.object(bl, "wait_for_session_cookies", _timeout_wait),
        patch.dict(sys.modules, {"playwright.async_api": pw_module}),
    ):
        ok = await bl.run_browser_login(notify=notify, timeout_minutes=1)

    assert ok is False
    assert any("timed out" in n for n in notes)


@pytest.mark.asyncio
async def test_run_browser_login_unexpected_error_notifies():
    async def spawn_fail(*args, pipe_output=False):
        raise FileNotFoundError("Xvfb not installed")

    notes = []

    async def notify(text):
        notes.append(text)

    with patch.object(bl, "_spawn", spawn_fail):
        ok = await bl.run_browser_login(notify=notify, timeout_minutes=1)

    assert ok is False
    assert any("Browser login failed" in n for n in notes)


def _async_noop():
    async def _noop(*args, **kwargs):
        return None

    return _noop


def _none():
    async def _inner(*args, **kwargs):
        return None

    return _inner


def test_main_entrypoint_exit_codes(monkeypatch):
    import teamsleech.browser_login_main as entry

    monkeypatch.setenv("BROWSER_LOGIN_TIMEOUT_MINUTES", "3")

    async def ok_run(**kwargs):
        return True

    monkeypatch.setattr(entry, "run_browser_login", ok_run)
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 0

    async def fail_run(**kwargs):
        return False

    monkeypatch.setattr(entry, "run_browser_login", fail_run)
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 1


def _commands_handlers():
    from unittest.mock import MagicMock

    from teamsleech.tg_bot.handlers.commands import register_commands

    handlers = {}
    mock_client = MagicMock()

    def on_message_deco(*args, **kwargs):
        def wrapper(fn):
            handlers[fn.__name__] = fn
            return fn

        return wrapper

    mock_client.on_message.side_effect = on_message_deco
    register_commands(mock_client, MagicMock(), MagicMock(), MagicMock())
    return handlers, mock_client


@pytest.mark.asyncio
async def test_browser_login_button_dispatches(monkeypatch):
    from unittest.mock import AsyncMock

    handlers, mock_client = _commands_handlers()
    assert "handle_browser_login_button" in handlers
    assert "handle_browser_login" in handlers

    dispatched = []

    async def fake_dispatch(wf):
        dispatched.append(wf)

    monkeypatch.setattr(
        "teamsleech.services.github_actions.dispatch_workflow", fake_dispatch
    )

    msg = AsyncMock()
    await handlers["handle_browser_login_button"](mock_client, msg)
    assert dispatched == ["browser-login.yml"]
    assert "Browser login starting" in msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_browser_login_button_dispatch_failure(monkeypatch):
    from unittest.mock import AsyncMock

    handlers, mock_client = _commands_handlers()

    async def boom(wf):
        raise RuntimeError("no PAT")

    monkeypatch.setattr(
        "teamsleech.services.github_actions.dispatch_workflow", boom
    )

    msg = AsyncMock()
    await handlers["handle_browser_login"](mock_client, msg)
    assert "Could not start" in msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_wait_for_local_origin_success(respx_mock):
    respx_mock.get("http://localhost:6080/vnc.html").mock(
        return_value=__import__("httpx").Response(200)
    )
    assert await bl.wait_for_local_origin(timeout=5, poll_seconds=0.01) is True


@pytest.mark.asyncio
async def test_wait_for_local_origin_never_up(respx_mock):
    respx_mock.get("http://localhost:6080/vnc.html").mock(
        return_value=__import__("httpx").Response(502)
    )
    assert await bl.wait_for_local_origin(timeout=0.1, poll_seconds=0.01) is False


@pytest.mark.asyncio
async def test_wait_for_public_tunnel_waits_for_200(respx_mock):
    route = respx_mock.get("https://abc.trycloudflare.com/vnc.html")
    route.side_effect = [
        __import__("httpx").Response(502),
        __import__("httpx").Response(200),
    ]
    status = await bl.wait_for_public_tunnel(
        "https://abc.trycloudflare.com", timeout=5, poll_seconds=0.01
    )
    assert status == 200


@pytest.mark.asyncio
async def test_wait_for_public_tunnel_stays_broken(respx_mock):
    respx_mock.get("https://abc.trycloudflare.com/vnc.html").mock(
        return_value=__import__("httpx").Response(502)
    )
    status = await bl.wait_for_public_tunnel(
        "https://abc.trycloudflare.com", timeout=0.1, poll_seconds=0.01
    )
    assert status == 502


@pytest.mark.asyncio
async def test_run_browser_login_local_origin_failure():
    context = FakeContext([[]])
    context.pages = [types.SimpleNamespace(goto=_async_noop())]
    pw_module, _ = _fake_playwright(context)
    notes = []

    async def notify(text):
        notes.append(text)

    async def local_down(**kwargs):
        return False

    with (
        patch.object(bl, "_spawn", _fake_spawn(["https://x-y.trycloudflare.com\n"])),
        patch.object(bl, "wait_for_local_origin", local_down),
        patch.dict(sys.modules, {"playwright.async_api": pw_module}),
    ):
        ok = await bl.run_browser_login(notify=notify, timeout_minutes=1)

    assert ok is False
    assert any("local viewer never came up" in n for n in notes)


@pytest.mark.asyncio
async def test_run_browser_login_public_tunnel_failure():
    context = FakeContext([[]])
    context.pages = [types.SimpleNamespace(goto=_async_noop())]
    pw_module, _ = _fake_playwright(context)
    notes = []

    async def notify(text):
        notes.append(text)

    async def healthy_local(**kwargs):
        return True

    async def tunnel_broken(*args, **kwargs):
        return 502

    with (
        patch.object(bl, "_spawn", _fake_spawn(["https://x-y.trycloudflare.com\n"])),
        patch.object(bl, "wait_for_local_origin", healthy_local),
        patch.object(bl, "wait_for_public_tunnel", tunnel_broken),
        patch.dict(sys.modules, {"playwright.async_api": pw_module}),
    ):
        ok = await bl.run_browser_login(notify=notify, timeout_minutes=1)

    assert ok is False
    assert any("never came online" in n for n in notes)


@pytest.mark.asyncio
async def test_run_browser_login_helper_crash_detected():
    context = FakeContext([[]])
    context.pages = [types.SimpleNamespace(goto=_async_noop())]
    pw_module, _ = _fake_playwright(context)
    notes = []

    async def notify(text):
        notes.append(text)

    async def spawn_with_dead(*args, pipe_output=False):
        proc = FakeProc(["https://x-y.trycloudflare.com\n"] if pipe_output else [])
        if args[0] == "websockify":
            proc.returncode = 1  # died at startup
        return proc

    with (
        patch.object(bl, "_spawn", spawn_with_dead),
        patch.dict(sys.modules, {"playwright.async_api": pw_module}),
    ):
        ok = await bl.run_browser_login(notify=notify, timeout_minutes=1)

    assert ok is False
    assert any("Browser login failed" in n for n in notes)
