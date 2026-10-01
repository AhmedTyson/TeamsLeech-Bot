from teamsleech.tg_bot.callbacks import is_valid_team_id, parse_callback_index


class TestParseCallbackIndex:
    def test_valid(self):
        assert parse_callback_index("ren:0") == 0
        assert parse_callback_index("sug:12") == 12
        assert parse_callback_index("srch_pg:3") == 3
        assert parse_callback_index("del_subj:7") == 7
        assert parse_callback_index("del_confirm:1") == 1

    def test_malformed(self):
        assert parse_callback_index("ren:abc") is None
        assert parse_callback_index("ren:") is None
        assert parse_callback_index("ren:-1") is None
        assert parse_callback_index("del_subj:-1") is None
        assert parse_callback_index("ren:1:2") is None
        assert parse_callback_index("sel:all") is None
        assert parse_callback_index("") is None
        assert parse_callback_index(None) is None
        assert parse_callback_index("ren:999999999999999999999") == 999999999999999999999


class TestIsValidTeamId:
    def test_uuid_ok(self):
        assert is_valid_team_id("123e4567-e89b-12d3-a456-426614174000")

    def test_rejects(self):
        assert not is_valid_team_id("a:b")
        assert not is_valid_team_id("")
        assert not is_valid_team_id(None)
        assert not is_valid_team_id("has space")
        assert not is_valid_team_id("x" * 65)
