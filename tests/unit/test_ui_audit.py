"""UI audit: every button the bot shows must have a registered handler,
and the one-tap login affordances must be wired end to end."""

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "teamsleech"

META = set(".^$*+?[](){}|\\")


def _read_all():
    return {
        p: p.read_text(encoding="utf-8")
        for p in SRC.rglob("*.py")
    }


def _literal_prefix(pattern: str) -> str:
    """Literal head of a regex or f-string callback literal."""
    pattern = pattern.lstrip("^")
    out = []
    for ch in pattern:
        if ch in META or ch == "{":
            break
        out.append(ch)
    return "".join(out)


def _emitted_callbacks(sources) -> set[str]:
    emitted = set()
    for text in sources.values():
        for m in re.finditer(r'callback_data\s*=\s*f?"([^"]+)"', text):
            prefix = _literal_prefix(m.group(1))
            if prefix and prefix != "cal:noop":
                emitted.add(prefix)
    return emitted


def _registered_callback_prefixes(sources) -> set[str]:
    """Literal prefixes of regexes on callback-query handlers."""
    prefixes = set()
    for text in sources.values():
        for block in re.split(r"@app\.", text):
            if "on_callback_query" not in block.split("\n", 2)[0] + block:
                pass
        for m in re.finditer(
            r'on_callback_query\(.*?filters\.regex\(\s*r?"([^"]+)"',
            text,
            re.DOTALL,
        ):
            prefix = _literal_prefix(m.group(1))
            if prefix:
                prefixes.add(prefix)
    return prefixes


def test_every_emitted_callback_has_a_handler():
    sources = _read_all()
    emitted = _emitted_callbacks(sources)
    handlers = _registered_callback_prefixes(sources)
    missing = []
    for e in sorted(emitted):
        if not any(e.startswith(h) or h.startswith(e) for h in handlers):
            missing.append(e)
    assert not missing, f"callback_data with no handler: {missing}"


def test_every_reply_keyboard_button_has_a_handler():
    from teamsleech.tg_bot.keyboards import REPLY_KEYBOARD

    sources = _read_all()
    message_regexes = set()
    for text in sources.values():
        for m in re.finditer(
            r'on_message\(.*?filters\.regex\(\s*r?"([^"]+)"',
            text,
            re.DOTALL,
        ):
            message_regexes.add(m.group(1).strip("^$"))

    for row in REPLY_KEYBOARD.keyboard:
        for btn in row:
            assert btn.text in message_regexes, (
                f"reply-keyboard button '{btn.text}' has no message handler"
            )


def test_failure_keyboard_gating():
    from teamsleech.tg_bot.handlers.upload_ui import _failure_keyboard

    assert _failure_keyboard("SharePoint download failed [401]") is not None
    assert _failure_keyboard("session expired") is not None
    assert _failure_keyboard("Telegram upload timed out") is None


@pytest.mark.asyncio
async def test_login_start_callback_triggers_reauth(monkeypatch):
    from teamsleech.tg_bot.handlers import commands

    reauth = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "teamsleech.services.reauth.run_reauth_flow", reauth
    )
    monkeypatch.setattr(
        "teamsleech.services.auth.authenticate", AsyncMock(return_value="tok")
    )

    handlers = {}
    client = MagicMock()

    def on_cb(*args, **kwargs):
        def wrapper(func):
            handlers[func.__name__] = func
            return func
        return wrapper

    client.on_callback_query.side_effect = on_cb
    client.on_message.side_effect = lambda *a, **k: (lambda f: f)

    scanner = MagicMock()
    state = MagicMock()
    discovery = MagicMock()
    discovery.graph = MagicMock()
    commands.register_commands(client, scanner, state, discovery)

    cb = AsyncMock()
    cb.data = "login:start"
    cb.message = AsyncMock()
    await handlers["handle_login_cb"](client, cb)

    reauth.assert_awaited_once()
    cb.message.reply.assert_awaited()


@pytest.mark.asyncio
async def test_login_button_points_to_registered_handler():
    from teamsleech.tg_bot.handlers.upload_ui import LOGIN_BUTTON_KB

    data = LOGIN_BUTTON_KB.inline_keyboard[0][0].callback_data
    sources = _read_all()
    handlers = _registered_callback_prefixes(sources)
    assert any(
        data.startswith(h) or h.startswith(data) for h in handlers
    ), f"login button '{data}' has no registered callback handler"
