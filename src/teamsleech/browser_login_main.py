"""Entrypoint for the browser-login workflow run.

Started by .github/workflows/browser-login.yml (dispatched from the bot's
🖥 Browser Login button). Exits 0 when cookies were saved, 1 otherwise.
"""

import asyncio
import logging
import os

from teamsleech.services.browser_login import run_browser_login


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    site = os.getenv("SP_LOGIN_URL") or None
    timeout = int(os.getenv("BROWSER_LOGIN_TIMEOUT_MINUTES", "12"))
    ok = asyncio.run(run_browser_login(site_url=site, timeout_minutes=timeout))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
