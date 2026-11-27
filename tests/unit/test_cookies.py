import json
from unittest.mock import AsyncMock

from teamsleech.core.config import settings
from teamsleech.services.cookies import (
    cookie_header,
    load_cookies,
    merge_refreshed_cookies,
    persist_refreshed_cookies,
)


class TestLoadCookies:
    def test_valid_list(self):
        raw = '[{"name": "FedAuth", "value": "abc", "domain": "x.sharepoint.com"}]'
        assert load_cookies(raw) == [{"name": "FedAuth", "value": "abc"}]

    def test_dict_wrapped(self):
        raw = '{"cookies": [{"name": "a", "value": "1"}]}'
        assert load_cookies(raw) == [{"name": "a", "value": "1"}]

    def test_empty_returns_empty(self):
        assert load_cookies("") == []
        assert load_cookies("   ") == []

    def test_invalid_json_returns_empty(self):
        assert load_cookies("not json") == []

    def test_non_list_returns_empty(self):
        assert load_cookies('{"a": 1}') == []
        assert load_cookies('"str"') == []

    def test_entries_without_name_skipped(self):
        raw = '[{"value": "x"}, {"name": "a", "value": "1"}, "junk", 5]'
        assert load_cookies(raw) == [{"name": "a", "value": "1"}]


class TestCookieHeader:
    def test_joins_pairs(self):
        cookies = [{"name": "a", "value": "1"}, {"name": "b", "value": "2"}]
        assert cookie_header(cookies) == "a=1; b=2"

    def test_skips_nameless(self):
        assert cookie_header([{"name": "", "value": "x"}]) == ""


class TestMergeRefreshedCookies:
    def test_updates_changed_values(self):
        raw = '[{"name": "rtFa", "value": "old", "domain": ".sharepoint.com"}]'
        new_json, changed = merge_refreshed_cookies(
            raw, [{"name": "rtFa", "value": "new"}]
        )
        assert changed == ["rtFa"]
        items = json.loads(new_json)
        # Value updated; untouched fields (domain) preserved.
        assert items == [
            {"name": "rtFa", "value": "new", "domain": ".sharepoint.com"}
        ]

    def test_no_change_returns_none(self):
        raw = '[{"name": "rtFa", "value": "same"}]'
        assert merge_refreshed_cookies(
            raw, [{"name": "rtFa", "value": "same"}]
        ) == (None, [])

    def test_adopts_missing_session_markers(self):
        raw = '[{"name": "other", "value": "1"}]'
        new_json, changed = merge_refreshed_cookies(
            raw, [{"name": "FedAuth", "value": "f"}]
        )
        assert changed == ["FedAuth"]
        items = json.loads(new_json)
        assert {c["name"] for c in items} == {"other", "FedAuth"}

    def test_non_marker_unknown_names_not_adopted(self):
        raw = '[{"name": "other", "value": "1"}]'
        assert merge_refreshed_cookies(
            raw, [{"name": "random", "value": "r"}]
        ) == (None, [])

    def test_dict_shape_preserved(self):
        raw = '{"cookies": [{"name": "rtFa", "value": "old"}]}'
        new_json, changed = merge_refreshed_cookies(
            raw, [{"name": "rtFa", "value": "new"}]
        )
        assert changed == ["rtFa"]
        assert json.loads(new_json) == {
            "cookies": [{"name": "rtFa", "value": "new"}]
        }

    def test_invalid_or_empty_saved_returns_none(self):
        fresh = [{"name": "rtFa", "value": "new"}]
        assert merge_refreshed_cookies("", fresh) == (None, [])
        assert merge_refreshed_cookies("not json", fresh) == (None, [])
        assert merge_refreshed_cookies('{"a": 1}', fresh) == (None, [])

    def test_empty_fresh_returns_none(self):
        raw = '[{"name": "rtFa", "value": "old"}]'
        assert merge_refreshed_cookies(raw, []) == (None, [])
        assert merge_refreshed_cookies(raw, [{"name": "", "value": "x"}]) == (
            None,
            [],
        )


class TestPersistRefreshedCookies:
    async def test_rotates_and_updates_settings(self, monkeypatch):
        monkeypatch.setattr(
            settings, "sp_cookies_json", '[{"name": "rtFa", "value": "old"}]'
        )
        calls = {}

        async def fake_rotate(name, value):
            calls[name] = value

        monkeypatch.setattr(
            "teamsleech.services.github_secrets.rotate_github_secret", fake_rotate
        )
        changed = await persist_refreshed_cookies(
            [{"name": "rtFa", "value": "new"}]
        )
        assert changed == ["rtFa"]
        assert json.loads(calls["SP_COOKIES_JSON"]) == [
            {"name": "rtFa", "value": "new"}
        ]
        assert settings.sp_cookies_json == calls["SP_COOKIES_JSON"]

    async def test_noop_when_unchanged(self, monkeypatch):
        monkeypatch.setattr(
            settings, "sp_cookies_json", '[{"name": "rtFa", "value": "same"}]'
        )
        rotate = AsyncMock(side_effect=AssertionError("must not rotate"))
        monkeypatch.setattr(
            "teamsleech.services.github_secrets.rotate_github_secret", rotate
        )
        assert await persist_refreshed_cookies(
            [{"name": "rtFa", "value": "same"}]
        ) == []
        rotate.assert_not_called()

    async def test_rotation_failure_never_raises(self, monkeypatch):
        monkeypatch.setattr(
            settings, "sp_cookies_json", '[{"name": "rtFa", "value": "old"}]'
        )
        rotate = AsyncMock(side_effect=RuntimeError("github down"))
        monkeypatch.setattr(
            "teamsleech.services.github_secrets.rotate_github_secret", rotate
        )
        assert await persist_refreshed_cookies(
            [{"name": "rtFa", "value": "new"}]
        ) == []
