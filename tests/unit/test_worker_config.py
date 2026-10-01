import json

import pytest

from worker.config import Folder, load_folders


def _env(monkeypatch, folders):
    monkeypatch.setenv("FOLDERS_JSON", json.dumps(folders))
    monkeypatch.delenv("FOLDERS_PATH", raising=False)


def test_loads_list(monkeypatch):
    _env(monkeypatch, [{"name": "DS", "url": "https://x.sharepoint.com/sites/A/Rec"}])
    folders = load_folders()
    assert folders == [Folder(name="DS", url="https://x.sharepoint.com/sites/A/Rec")]


def test_loads_dict_wrapper_and_strips_slash(monkeypatch):
    _env(
        monkeypatch,
        {"folders": [{"name": " DS ", "url": "https://x.sharepoint.com/s/"}]},
    )
    assert load_folders()[0].url == "https://x.sharepoint.com/s"


def test_missing_config_raises(monkeypatch):
    monkeypatch.delenv("FOLDERS_JSON", raising=False)
    monkeypatch.setattr("os.path.exists", lambda p: False)
    with pytest.raises(ValueError, match="No folders"):
        load_folders()


def test_bad_entries_raises(monkeypatch):
    for bad in (
        [{"name": "", "url": "https://x.sharepoint.com/s"}],
        [{"name": "A", "url": "http://x.sharepoint.com/s"}],
        [{"name": "A", "url": "https://example.com/s"}],
        [],
    ):
        _env(monkeypatch, bad)
        with pytest.raises(ValueError):
            load_folders()


def test_malformed_json_raises(monkeypatch):
    monkeypatch.setenv("FOLDERS_JSON", "{nope")
    monkeypatch.delenv("FOLDERS_PATH", raising=False)
    with pytest.raises(ValueError, match="not valid JSON"):
        load_folders()
