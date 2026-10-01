"""Mint an initial Microsoft refresh token (first-time setup only).

For re-authorizing an existing deployment, prefer the guided flow:
workflow_dispatch with mode=reauth (code via Telegram + auto-inject).

The token is written to `teams_refresh_token.txt` (owner-only perms) —
never printed — then copy it into TEAMS_REFRESH_TOKEN and delete the file.

Usage
-----
    python scripts/get_teams_token.py
"""

import asyncio
import os
from pathlib import Path

from teamsleech.services.reauth import run_device_reauth


def _print_code(uri: str, code: str) -> None:
    print("\n" + "=" * 60)
    print("ACTION REQUIRED:")
    print(f"1. Open your browser and go to: {uri}")
    print(f"2. Enter this code: {code}")
    print("=" * 60 + "\n")


async def _on_code(uri: str, code: str) -> None:
    _print_code(uri, code)


def _write_token(token: str) -> Path:
    out_path = Path("teams_refresh_token.txt")
    try:
        fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(token)
    except OSError:
        out_path.write_text(token)
        try:
            os.chmod(out_path, 0o600)
        except OSError:
            pass
    return out_path


def main() -> None:
    print("Requesting Device Code from Microsoft...")
    result = asyncio.run(run_device_reauth(_on_code))
    if result is None:
        msg = "Failed to authenticate."
        raise SystemExit(msg)
    _, refresh = result
    out_path = _write_token(refresh)
    print("\nSuccessfully authenticated!")
    print(f"\nRefresh token written to {out_path.resolve()} (owner-only perms).")
    print("Copy it into your TEAMS_REFRESH_TOKEN GitHub Secret, then delete the file.")
    print("Never paste it in chat, logs, or CI output. Do not run this in CI.")


if __name__ == "__main__":
    main()
