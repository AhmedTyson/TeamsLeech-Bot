import asyncio
import json

from worker.lister import FileEntry
from worker.run import run


def test_dry_run_lists_without_side_effects(tmp_path, monkeypatch, capsys):
    def fake_list(url, cookies, client):
        return [
            FileEntry(name="a.mp4", unique_id="u1", size=3, modified="", server_path="/s/a.mp4")
        ]

    def boom(*a, **k):
        msg = "must not download/upload in dry run"
        raise AssertionError(msg)

    notes = []
    monkeypatch.setenv(
        "FOLDERS_JSON",
        json.dumps([{"name": "C", "url": "https://t.sharepoint.com/sites/X/Shared Documents/"}]),
    )
    cookie_path = str(tmp_path / "cookies.txt")
    with open(cookie_path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(".example.com\tTRUE\t/\tTRUE\t9999999999\ta\t1\n")
    monkeypatch.setenv("MS_COOKIES_FILE", cookie_path)
    monkeypatch.setenv("DRY_RUN", "true")
    state_path = str(tmp_path / "processed.json")
    out = asyncio.run(
        run(str(tmp_path / "s.json"), str(tmp_path), fake_list, boom, boom, notes.append)
    )
    assert len(out) == 1 and out[0].tg_msg_id is None
    assert notes == []
    assert "would fetch" in capsys.readouterr().out
    import os

    assert not os.path.exists(state_path)
