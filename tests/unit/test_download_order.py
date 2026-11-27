"""Download candidate order: Graph's pre-authed URL bare first, then the
SharePoint token, cookies last. A rejected bearer or stale cookie must
never poison the tempauth URL that needs no auth."""

from teamsleech.core.config import settings
from teamsleech.services.transfer import TransferService

URL = (
    "https://uni.sharepoint.com/sites/team/_layouts/15/download.aspx"
    "?UniqueId=abc-123&e=x"
)


def _candidates(monkeypatch, cookies_json, token):
    monkeypatch.setattr(settings, "sp_cookies_json", cookies_json)
    svc = TransferService.__new__(TransferService)
    return svc._download_candidates(URL, token)


def _labels(cands):
    return [label for label, _, _ in cands]


def test_preauthed_first_with_token_and_cookies(monkeypatch):
    cands = _candidates(monkeypatch, '[{"name":"rtFa","value":"v"}]', "tok123")
    assert _labels(cands) == [
        "download.aspx (pre-authed)",
        "SharePoint REST $value",
        "download.aspx (user token)",
        "download.aspx (browser cookies)",
    ]
    # The pre-authed attempt must send no auth headers at all.
    assert cands[0][2] is None


def test_preauthed_first_without_token(monkeypatch):
    order = _labels(_candidates(monkeypatch, '[{"name":"rtFa","value":"v"}]', None))
    assert order == [
        "download.aspx (pre-authed)",
        "download.aspx (browser cookies)",
    ]


def test_preauthed_always_present(monkeypatch):
    for cookies_json, token in [
        ("", "tok123"),
        ("", None),
        ('[{"name":"rtFa","value":"v"}]', "tok123"),
        ('[{"name":"rtFa","value":"v"}]', None),
    ]:
        cands = _candidates(monkeypatch, cookies_json, token)
        assert cands[0][0] == "download.aspx (pre-authed)"
        assert cands[0][2] is None


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
