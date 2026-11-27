"""Remote self-login for SharePoint session cookies.

Runs a headed Chromium on the runner's virtual display (Xvfb), shares it to
the owner's phone through noVNC + a Cloudflare quick tunnel, and waits while
the owner logs into Microsoft himself. Credentials never touch the bot: the
remote page is the real login.microsoftonline.com, and the only thing this
module ever reads back is the resulting session cookies. When real
SharePoint session cookies (FedAuth/rtFa on sharepoint.com) appear, they
are written to the SP_COOKIES_JSON GitHub secret and the whole session
(tunnel, VNC, browser, profile) is torn down and wiped.
"""

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
from collections.abc import Awaitable, Callable

import httpx

from teamsleech.core.config import settings
from teamsleech.services.github_actions import dispatch_workflow
from teamsleech.services.github_secrets import rotate_github_secret

log = logging.getLogger("browser_login")

SITE_URL = (
    "https://commercehelwanedu.sharepoint.com"
    "/_layouts/15/sharepoint.aspx/discover"
)
COOKIE_SECRET = "SP_COOKIES_JSON"
BOT_RUNNER_WORKFLOW = "bot-runner.yml"

# Success markers: ONLY real SharePoint session cookies on a sharepoint.com
# domain. Login-flow cookies (RpsContextCookie, ESTSAUTH*, ...) are set by
# the login PAGE before any password is typed — counting them produced a
# false "session saved" that tore the tunnel down before the owner could
# even open it.
SESSION_MARKERS = ("FedAuth", "rtFa")
SESSION_DOMAIN = "sharepoint.com"
# Domains worth exporting even if tiny — login flow scatters state here.
KEEP_SUBSTRINGS = (
    "sharepoint.com",
    "microsoftonline.com",
    "msauth.net",
    "msauthimages.net",
    "office.com",
    "live.com",
    "microsoft.com",
)

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

XVFB_DISPLAY = ":99"
XVFB_SCREEN = "1280x800x24"
VNC_PORT = 5900
NOVNC_PORT = 6080
NOVNC_WEB = "/usr/share/novnc"
POLL_SECONDS = 5
TUNNEL_WAIT_SECONDS = 45
LOCAL_HEALTH_SECONDS = 30
PUBLIC_HEALTH_SECONDS = 90
DEFAULT_TIMEOUT_MINUTES = 12

Notify = Callable[[str], Awaitable[None]]


def generate_password() -> str:
    """Short random VNC password (VNC truncates at 8 chars)."""
    return secrets.token_urlsafe(6)


def parse_tunnel_url(text: str) -> str | None:
    """Extract the trycloudflare URL from cloudflared log output."""
    match = TUNNEL_URL_RE.search(text)
    return match.group(0) if match else None


def filter_session_cookies(
    all_cookies: list[dict],
) -> tuple[list[dict], list[str]]:
    """Keep auth-relevant domains; return (kept, session markers found).

    A marker only counts when it lives on the SharePoint domain — the same
    cookie name anywhere else does not prove a SharePoint session.
    """
    kept = [
        c
        for c in all_cookies
        if any(s in (c.get("domain") or "") for s in KEEP_SUBSTRINGS)
    ]
    found = [
        m
        for m in SESSION_MARKERS
        if any(
            c.get("name") == m and SESSION_DOMAIN in (c.get("domain") or "")
            for c in kept
        )
    ]
    return kept, found


def export_cookie_list(kept: list[dict]) -> list[dict]:
    """Shape cookies for SP_COOKIES_JSON (same as scripts/grab_cookies.py)."""
    return [
        {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
        }
        for c in kept
        if c.get("name")
    ]


async def notify_owner(text: str) -> None:
    """DM the owner via the Bot API (no pyrogram client in this run)."""
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=15.0,
        )
        resp.raise_for_status()


async def _spawn(
    *args: str, pipe_output: bool = False
) -> asyncio.subprocess.Process:
    """Spawn a helper. Output is inherited (lands in the run log) except
    for the tunnel, whose output we parse for the public URL."""
    if pipe_output:
        return await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    return await asyncio.create_subprocess_exec(*args)


async def _http_status(url: str, timeout: float = 8.0) -> int | None:
    """GET a URL and return its HTTP status, or None on network error."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=timeout)
            return resp.status_code
    except Exception as exc:
        log.debug("health probe %s failed: %s", url, exc)
        return None


async def wait_for_local_origin(
    port: int = NOVNC_PORT,
    timeout: int = LOCAL_HEALTH_SECONDS,
    poll_seconds: float = 1.0,
) -> bool:
    """Wait until noVNC's web page answers on localhost."""
    url = f"http://localhost:{port}/vnc.html"
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        status = await _http_status(url)
        log.info("Local noVNC health: %s -> %s", url, status)
        if status == 200:
            return True
        await asyncio.sleep(poll_seconds)
    return False


async def wait_for_public_tunnel(
    tunnel_url: str,
    timeout: int = PUBLIC_HEALTH_SECONDS,
    poll_seconds: float = 3.0,
) -> int | None:
    """Wait until the public tunnel URL answers 200 end-to-end.

    cloudflared prints the URL before the tunnel is registered at the edge
    (early clicks see Cloudflare 1033), and a dead origin gives a 502 — so
    the link only goes out after this returns 200.
    """
    url = tunnel_url.rstrip("/") + "/vnc.html"
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last: int | None = None
    while loop.time() < deadline:
        last = await _http_status(url)
        log.info("Public tunnel health: %s -> %s", url, last)
        if last == 200:
            return last
        await asyncio.sleep(poll_seconds)
    return last


async def _wait_tunnel_url(
    proc: asyncio.subprocess.Process, timeout: int = TUNNEL_WAIT_SECONDS
) -> str | None:
    """Read cloudflared output until the public tunnel URL appears."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if proc.stdout is None:
            return None
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
        except TimeoutError:
            continue
        if not line:
            return None
        url = parse_tunnel_url(line.decode(errors="replace"))
        if url:
            return url
    return None


def _dead_helpers(procs: list[tuple[str, asyncio.subprocess.Process]]) -> list[str]:
    """Names of helper processes that already exited."""
    return [name for name, p in procs if p.returncode is not None]


async def wait_for_session_cookies(
    context,
    timeout_seconds: float,
    poll_seconds: float = POLL_SECONDS,
) -> tuple[list[dict], list[str]]:
    """Poll the browser until SharePoint session cookies appear."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_seconds
    last_count = -1
    while loop.time() < deadline:
        try:
            cookies = await context.cookies()
        except Exception as exc:
            log.warning("Cookie poll failed: %s", exc)
            cookies = []
        kept, found = filter_session_cookies(cookies)
        if len(cookies) != last_count:
            log.info(
                "Cookies: %d total, %d auth-relevant, markers=%s",
                len(cookies),
                len(kept),
                found,
            )
            last_count = len(cookies)
        if found:
            return kept, found
        await asyncio.sleep(poll_seconds)
    raise TimeoutError(
        f"No SharePoint session cookies within {timeout_seconds:.0f}s"
    )


async def run_browser_login(
    notify: Notify = notify_owner,
    site_url: str | None = None,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
    dispatch_followup: bool = True,
) -> bool:
    """Run one remote self-login session. Returns True on cookies saved."""
    site = site_url or os.getenv("SP_LOGIN_URL") or SITE_URL
    procs: list[tuple[str, asyncio.subprocess.Process]] = []
    tmpdir = tempfile.mkdtemp(prefix="sp-login-")
    pw = None
    context = None
    password = generate_password()
    try:
        procs.append(
            ("Xvfb", await _spawn("Xvfb", XVFB_DISPLAY, "-screen", "0", XVFB_SCREEN))
        )
        await asyncio.sleep(2)

        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        context = await pw.chromium.launch_persistent_context(
            os.path.join(tmpdir, "profile"),
            headless=False,
            env={**os.environ, "DISPLAY": XVFB_DISPLAY},
            args=[
                "--no-sandbox",
                "--no-first-run",
                "--no-default-browser-check",
                "--start-maximized",
            ],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(site)

        procs.append(
            (
                "x11vnc",
                await _spawn(
                    "x11vnc",
                    "-display",
                    XVFB_DISPLAY,
                    "-forever",
                    "-shared",
                    "-rfbport",
                    str(VNC_PORT),
                    "-passwd",
                    password,
                ),
            )
        )
        procs.append(
            (
                "websockify",
                await _spawn(
                    "websockify",
                    "--web",
                    NOVNC_WEB,
                    str(NOVNC_PORT),
                    f"localhost:{VNC_PORT}",
                ),
            )
        )
        tunnel = await _spawn(
            "cloudflared",
            "tunnel",
            "--url",
            f"http://localhost:{NOVNC_PORT}",
            "--no-autoupdate",
            pipe_output=True,
        )
        procs.append(("cloudflared", tunnel))

        # Give helpers a moment, then fail loudly if any died on startup.
        await asyncio.sleep(3)
        dead = _dead_helpers(procs)
        if dead:
            raise RuntimeError(f"helper process(es) died at startup: {', '.join(dead)}")

        url = await _wait_tunnel_url(tunnel)
        if not url:
            await notify(
                "❌ Browser login could not start its secure link."
                " Please tap 🖥 Browser Login again."
            )
            return False

        # Health gate: the link only goes out once it actually works.
        if not await wait_for_local_origin():
            await notify(
                "❌ Browser login's local viewer never came up."
                " Please tap 🖥 Browser Login again."
            )
            return False
        public_status = await wait_for_public_tunnel(url)
        if public_status != 200:
            await notify(
                "❌ The login link never came online"
                f" (last status: {public_status})."
                " Please tap 🖥 Browser Login again."
            )
            return False
        log.info("Tunnel verified live: %s returned 200.", url)

        await notify(
            "🖥 **Browser login ready**\n\n"
            f"1. Open: {url}\n"
            f"2. Password: `{password}`\n"
            "3. Log into Microsoft in the remote browser — your password and"
            " MFA go only to Microsoft's real page, never to the bot.\n"
            "4. Wait for the SharePoint site to load. I detect the sign-in"
            " and save the session myself.\n\n"
            f"⏳ The link stays open for up to {timeout_minutes} minutes."
        )

        kept, found = await wait_for_session_cookies(
            context, timeout_minutes * 60
        )
        exported = export_cookie_list(kept)
        await rotate_github_secret(COOKIE_SECRET, json.dumps(exported))
        log.info(
            "Saved %d cookies (%d markers) to %s",
            len(exported),
            len(found),
            COOKIE_SECRET,
        )

        msg = (
            f"✅ **Session saved** ({len(found)} sign-in markers,"
            f" {len(exported)} cookies).\n"
        )
        if dispatch_followup:
            try:
                await dispatch_workflow(BOT_RUNNER_WORKFLOW)
                msg += (
                    "🚀 A fresh check run is starting — when it's live, tap"
                    " 🔍 Check Recordings and download again. No login needed."
                )
            except Exception as exc:
                log.warning("Follow-up dispatch failed: %s", exc)
                msg += (
                    "Start a new run (Actions → TeamsLeech Bot → Run"
                    " workflow) and download again."
                )
        await notify(msg)
        return True
    except TimeoutError:
        await notify(
            "⌛ Browser login timed out — no sign-in detected in time."
            " Tap 🖥 Browser Login to try again."
        )
        return False
    except Exception as exc:
        log.exception("Browser login failed")
        await notify(f"❌ Browser login failed: `{exc}`")
        return False
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if pw is not None:
            try:
                await pw.stop()
            except Exception:
                pass
        for _, proc in procs:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
        if procs:
            await asyncio.gather(
                *(p.wait() for _, p in procs), return_exceptions=True
            )
        shutil.rmtree(tmpdir, ignore_errors=True)
        log.info("Browser login session cleaned up.")
