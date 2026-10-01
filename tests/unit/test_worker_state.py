import json
import os

import pytest

from worker.state import is_new, load, mark, save


def test_roundtrip(tmp_path):
    path = str(tmp_path / "processed.json")
    assert load(path) == {}
    state = mark({}, "id1", "Lecture05.mp4", 123)
    assert not is_new("id1", state)
    assert is_new("id2", state)
    save(state, path)
    back = load(path)
    assert back["id1"] == {"name": "Lecture05.mp4", "tg_msg_id": 123}


def test_corrupt_file_loads_empty(tmp_path):
    path = str(tmp_path / "p.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{oops")
    with pytest.raises(json.JSONDecodeError):
        load(path)


def test_save_atomic_no_tmp_left(tmp_path):
    path = str(tmp_path / "p.json")
    save({"a": {"name": "x", "tg_msg_id": None}}, path)
    leftovers = [p for p in os.listdir(str(tmp_path)) if p.endswith(".tmp")]
    assert leftovers == []
    assert load(path)["a"]["tg_msg_id"] is None
