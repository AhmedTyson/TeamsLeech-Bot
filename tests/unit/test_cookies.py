from teamsleech.services.cookies import cookie_header, load_cookies


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
