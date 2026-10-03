# Cookie Download (proven path)

Token downloads can be denied tenant-side while your browser downloads fine.
The bot then falls back to your browser session: it sends your exported
cookies with the download request, so SharePoint sees exactly the session
that works when you click. This is the path that delivered files on Oct 2.

## One-time setup (2 min, no portal, no admin)

1. In your desktop browser, open any page on
   `https://commercehelwanedu.sharepoint.com` while logged in.
2. Install the **Cookie-Editor** (or EditThisCookie) extension.
3. Click it → **Export** → **as JSON** (clipboard).
4. GitHub repo → Settings → Secrets → Actions → New secret:
   name `SP_COOKIES_JSON`, value = pasted JSON.
5. Re-run the workflow (any mode). First download attempt per file now uses
   cookies — watch for `Trying download.aspx (browser cookies)`.

## Expiry

Browser sessions expire (days–weeks). When a download fails with
`browser cookies rejected too — session expired, re-export SP_COOKIES_JSON`,
repeat steps 1–4 (overwrite the secret) — no code change, no re-login flow.

## Order of attempts per file

1. `download.aspx (browser cookies)` — only when `SP_COOKIES_JSON` is set
2. `SharePoint REST $value` (user token)
3. `download.aspx (user token)` or `(anonymous)` fallback

The failure message lists every attempt with its status.
