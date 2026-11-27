"""Download candidate order: SharePoint token first, cookies as fallback."""

from teamsleech.core.config import settings
from teamsleech.services.transfer import TransferService

URL = (
    "https://uni.sharepoint.com/sites/team/_layouts/15/download.aspx"
    "?UniqueId=abc-123&e=x"
)


def _candidates(monkeypatch, cookies_json, token):
    monkeypatch.setattr(settings, "sp_cookies_json", cookies_json)
    svc = TransferService.__new__(TransferService)
    return [label for label, _, _ in svc._download_candidates(URL, token)]


def test_token_first_cookies_fallback(monkeypatch):
    order = _candidates(monkeypatch, '[{"name":"rtFa","value":"v"}]', "tok123")
    assert order == [
        "SharePoint REST $value",
        "download.aspx (user token)",
        "download.aspx (browser cookies)",
    ]


def test_no_token_cookies_then_anonymous(monkeypatch):
    order = _candidates(monkeypatch, '[{"name":"rtFa","value":"v"}]', None)
    assert order == [
        "download.aspx (browser cookies)",
        "download.aspx (anonymous)",
    ]


def test_token_without_cookies_never_anonymous(monkeypatch):
    order = _candidates(monkeypatch, "", "tok123")
    assert order == ["SharePoint REST $value", "download.aspx (user token)"]
    assert "download.aspx (anonymous)" not in order


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
    assert "🔑 Microsoft Login" in labels
