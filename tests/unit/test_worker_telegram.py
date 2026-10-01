from unittest.mock import MagicMock, patch

from worker.telegram import notify


def test_notify_plain_text_no_markdown(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    seen = {}

    def fake_post(url, json=None, timeout=None):
        seen.update(json)
        resp = MagicMock()
        resp.json.return_value = {"result": {"message_id": 5}}
        return resp

    with patch("worker.telegram.httpx.post", side_effect=fake_post):
        assert notify("a_b (c)") == 5
    assert "parse_mode" not in seen
    assert seen["text"] == "a_b (c)"


def test_notify_skipped_without_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert notify("hi") is None
