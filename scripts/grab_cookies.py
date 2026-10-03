"""Export SharePoint browser cookies for SP_COOKIES_JSON.

Opens a real browser window on your SharePoint tenant. You log in as usual
(SSO/MFA all fine), browse anywhere on the site, then press ENTER here.
Cookies are dumped as JSON — paste into the SP_COOKIES_JSON GitHub secret.

Usage:
    pip install playwright
    playwright install chromium
    python scripts/grab_cookies.py
"""

import json
import sys

SITE_URL = "https://commercehelwanedu.sharepoint.com/sites/BIS-DataSecurity-Dr.HanyGouda-L4"
OUT_FILE = "sp_cookies.json"
MARKERS = ("FedAuth", "rtFa", "ESTSAUTH", "ESTSAUTHPERSISTENT")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed. Run:")
        print("  pip install playwright && playwright install chromium")
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(SITE_URL)
        print("=" * 60)
        print("1. Log in to Microsoft in the opened window.")
        print("2. Make sure the SharePoint site loads.")
        print("3. Come back here and press ENTER.")
        print("=" * 60)
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 1

        cookies = [
            {"name": c["name"], "value": c["value"]}
            for c in context.cookies()
            if "sharepoint.com" in (c.get("domain") or "")
        ]
        browser.close()

    names = {c["name"] for c in cookies}
    print(f"Captured {len(cookies)} sharepoint.com cookies: {sorted(names)}")
    if not any(m in names for m in MARKERS):
        print("WARNING: no session cookies found — you may not be logged in.")
        print("Log in fully and run again.")
        return 1

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f)
    print(f"Saved to {OUT_FILE}. Paste its contents into SP_COOKIES_JSON.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
