"""Phase-0 spike: can a transplanted browser session list SharePoint on GHA?

GO/NO-GO gate for the browser-session migration. Reads Netscape cookies.txt
(path in MS_COOKIES_FILE), injects into headless Chromium, and lists 5 items
from a team Documents library via SharePoint REST (same-cookie context).

Exit 0 + filenames  => GO. Login redirect / 401 / empty => NO-GO, loudly.
"""

import os
import sys
from http.cookiejar import MozillaCookieJar

SITE = os.environ.get(
    "SPIKE_SITE",
    "https://commercehelwanedu.sharepoint.com/sites/BIS-ForeignTrade-Dr.ShaimaaWehbe-L4",
)
LIST_URL = (
    SITE + "/_api/web/lists/getbytitle('Documents')/items?$select=FileLeafRef,FileDirRef&$top=5"
)


def load_cookies(path: str) -> list[dict]:
    jar = MozillaCookieJar(path)
    jar.load(ignore_discard=True, ignore_expires=True)
    return [
        {"name": c.name, "value": c.value or "", "domain": c.domain, "path": c.path} for c in jar
    ]


def main() -> int:
    cookie_file = os.environ.get("MS_COOKIES_FILE", "cookies.txt")
    if not os.path.exists(cookie_file):
        print("NO-GO: cookie file missing (MS_COOKIES_FILE not restored).")
        return 2
    cookies = load_cookies(cookie_file)
    print(f"loaded {len(cookies)} cookies")
    if not cookies:
        print("NO-GO: cookie jar empty.")
        return 2
    from playwright.sync_api import sync_playwright  # lazy: CI installs it

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        ctx.add_cookies(cookies)
        resp = ctx.request.get(LIST_URL, headers={"Accept": "application/json;odata=verbose"})
        print(f"REST status: {resp.status}")
        if resp.status == 401:
            ctx.storage_state(path="spike-failed.json")
            browser.close()
            print("NO-GO: 401 — session rejected (expiry or CA block).")
            return 1
        try:
            items = resp.json()["d"]["results"]
        except Exception as exc:
            print(f"NO-GO: unexpected payload: {exc}")
            browser.close()
            return 1
        names = [i.get("FileLeafRef", "?") for i in items]
        print(f"GO: listed {len(names)} items: {names}")
        browser.close()
        if not names:
            print("NO-GO: empty listing (auth wall or wrong library).")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
