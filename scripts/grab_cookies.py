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

SITE_URL = "https://commercehelwanedu.sharepoint.com/_layouts/15/sharepoint.aspx/discover"
OUT_FILE = "sp_cookies.json"
# Legacy (FedAuth/rtFa) + current Entra/SharePoint session markers.
# NOTE: ESTSAUTH* often lives on login.microsoftonline.com, SPOIDCRL on
# *.sharepoint.com — so markers must be checked across ALL domains, not
# just sharepoint.com (the old domain filter hid them).
MARKERS = (
    "FedAuth",
    "rtFa",
    "SPOIDCRL",
    "ESTSAUTH",
    "ESTSAUTHPERSISTENT",
    "ESTSAUTHLIGHT",
    "STSServiceCookie",
    "RpsContextCookie",
)
# Domains worth keeping even if tiny — login flow scatters session state here.
KEEP_SUBSTRINGS = (
    "sharepoint.com",
    "microsoftonline.com",
    "msauth.net",
    "msauthimages.net",
    "office.com",
    "live.com",
    "microsoft.com",
)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=SITE_URL, help="SharePoint page to open")
    ap.add_argument("--out", default=OUT_FILE, help="JSON file to write")
    ap.add_argument(
        "--all", action="store_true",
        help="also dump unrelated cookies (default: only auth-relevant domains)",
    )
    args = ap.parse_args()
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
        page.goto(args.url)
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

        all_cookies = context.cookies()
        browser.close()

    # Group by domain for display so nothing looks "missing".
    by_domain: dict[str, list[str]] = {}
    for c in all_cookies:
        by_domain.setdefault(c.get("domain") or "(no domain)", []).append(
            c.get("name") or ""
        )
    print(f"Captured {len(all_cookies)} cookies across {len(by_domain)} domains:")
    for dom in sorted(by_domain):
        print(f"  {dom}: {sorted(by_domain[dom])}")

    if args.all:
        kept = all_cookies
    else:
        kept = [
            c for c in all_cookies
            if any(s in (c.get("domain") or "") for s in KEEP_SUBSTRINGS)
        ]
        dropped = len(all_cookies) - len(kept)
        if dropped:
            print(f"Kept {len(kept)} auth-relevant cookies ({dropped} unrelated dropped).")
            print("Re-run with --all to keep everything.")

    cookies = [
        {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
        }
        for c in kept
        if c.get("name")
    ]
    names = {c["name"] for c in cookies}
    found = [m for m in MARKERS if any(n == m or n.startswith(m) for n in names)]
    print(f"Session markers found: {found or 'NONE'}")
    if not found:
        print("WARNING: no session cookies found — you may not be logged in.")
        print("Make sure the site loaded while logged in, then run again.")
        return 1

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cookies, f)
    print(f"Saved {len(cookies)} cookies to {args.out}.")
    print("Paste its contents into SP_COOKIES_JSON.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
