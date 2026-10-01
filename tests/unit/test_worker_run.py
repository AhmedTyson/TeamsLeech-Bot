import json
import os

import pytest

from worker.lister import FileEntry
from worker.run import entry_key, run, site_base


def _cookies(tmp_path):
    path = str(tmp_path / "cookies.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(".example.com\tTRUE\t/\tTRUE\t9999999999\ta\t1\n")
    return path


def test_site_base_and_entry_key():
    assert site_base("https://t.sharepoint.com/sites/X/Doc/") == "https://t.sharepoint.com"
    e = FileEntry(name="a", unique_id="", size=0, modified="", server_path="/s/a")
    assert entry_key(e) == "/s/a"


async def _noop_upload(path: str, caption: str) -> int:
    return 7


def test_run_new_and_dedup(tmp_path, monkeypatch):
    def fake_list(url, cookies, client):
        return [
            FileEntry(name="a.mp4", unique_id="u1", size=3, modified="", server_path="/s/a.mp4")
        ]

    async def fake_upload(path, caption):
        return 9

    def fake_download(url, cookies, dest, client):
        with open(dest, "wb") as f:
            f.write(b"abc")
        return 3, "hash"

    notes = []
    monkeypatch.setenv(
        "FOLDERS_JSON",
        json.dumps([{"name": "C", "url": "https://t.sharepoint.com/sites/X/Shared Documents/"}]),
    )
    monkeypatch.setenv("MS_COOKIES_FILE", _cookies(tmp_path))
    state_path = str(tmp_path / "processed.json")
    out = str(tmp_path / "out")
    os.makedirs(out)

    import asyncio

    first = asyncio.run(run(state_path, out, fake_list, fake_download, fake_upload, notes.append))
    assert len(first) == 1 and first[0].tg_msg_id == 9
    assert "New content detected" in notes[-1]
    second = asyncio.run(run(state_path, out, fake_list, fake_download, fake_upload, notes.append))
    assert second == []
    with open(state_path, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["u1"]["tg_msg_id"] == 9


def test_run_empty_cookies(tmp_path, monkeypatch):
    import asyncio

    monkeypatch.setenv(
        "FOLDERS_JSON",
        json.dumps([{"name": "C", "url": "https://t.sharepoint.com/sites/X/Shared Documents/"}]),
    )
    empty = str(tmp_path / "empty.txt")
    with open(empty, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("MS_COOKIES_FILE", empty)
    with pytest.raises(ValueError, match="No cookies"):
        asyncio.run(run(str(tmp_path / "s.json"), str(tmp_path)))
