"""Download candidate order: browser cookies first when configured (the
only route token-rejecting tenants serve; it fetches the /content
Location, never the pre-authed URL), then Graph's
@microsoft.graph.downloadUrl (pre-authenticated, tempauth) bare, then
SharePoint bearer routes; the bare /content redirect Location last (not
reliably pre-authenticated). A rejected bearer or stale cookie must
never poison the URL that needs no auth."""

from teamsleech.core.config import settings
from teamsleech.services.transfer import TransferService

URL = (
    "https://uni.sharepoint.com/sites/team/_layouts/15/download.aspx"
    "?UniqueId=abc-123&e=x"
)
PREAUTH = "https://uni.sharepoint.com/sites/team/_layouts/15/download.aspx?tempauth=tok"


def _candidates(monkeypatch, cookies_json, token, preauth=None):
    monkeypatch.setattr(settings, "sp_cookies_json", cookies_json)
    svc = TransferService.__new__(TransferService)
    return svc._download_candidates(URL, token, preauth)


def _labels(cands):
    return [label for label, _, _ in cands]


def test_cookies_first_with_token_and_cookies(monkeypatch):
    cands = _candidates(
        monkeypatch, '[{"name":"rtFa","value":"v"}]', "tok123", PREAUTH
    )
    assert _labels(cands) == [
        "download.aspx (browser cookies)",
        "Graph downloadUrl (pre-authed)",
        "SharePoint REST $value",
        "download.aspx (user token)",
        "download.aspx (no auth)",
    ]
    # The pre-authed attempt must send no auth headers at all.
    assert cands[1][1] == PREAUTH
    assert cands[1][2] is None


def test_no_downloadurl_without_token(monkeypatch):
    order = _labels(
        _candidates(monkeypatch, '[{"name":"rtFa","value":"v"}]', None)
    )
    assert order == [
        "download.aspx (browser cookies)",
        "download.aspx (no auth)",
    ]


def test_no_downloadurl_with_token(monkeypatch):
    order = _labels(_candidates(monkeypatch, "", "tok123"))
    assert order == [
        "SharePoint REST $value",
        "download.aspx (user token)",
        "download.aspx (no auth)",
    ]


def test_never_empty_candidates(monkeypatch):
    cands = _candidates(monkeypatch, "", None)
    assert _labels(cands) == ["download.aspx (no auth)"]


def test_rest_api_url_built_from_uniqueid(monkeypatch):
    monkeypatch.setattr(settings, "sp_cookies_json", "")
    svc = TransferService.__new__(TransferService)
    cands = svc._download_candidates(URL, "tok123")
    api = [u for label, u, _ in cands if label == "SharePoint REST $value"]
    assert api == [
        "https://uni.sharepoint.com/sites/team"
        "/_api/web/GetFileById('abc-123')/$value"
    ]


def test_login_button_in_reply_keyboard():
    from teamsleech.tg_bot.keyboards import REPLY_KEYBOARD

    labels = [b.text for row in REPLY_KEYBOARD.keyboard for b in row]
    assert "🖥 تسجيل الدخول" in labels
