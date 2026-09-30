def test_search_inputs_imports_rotate_from_github_secrets():
    import teamsleech.tg_bot.handlers.search_inputs as mod

    assert hasattr(mod, "register_search_inputs")
    assert hasattr(mod, "rotate_github_secret")

    from teamsleech.services import github_secrets

    assert mod.rotate_github_secret is github_secrets.rotate_github_secret


def test_register_all_handlers_imports_clean():
    from teamsleech.tg_bot.handlers import register_all_handlers

    assert callable(register_all_handlers)


class TestSearchShouldYield:
    def test_yields_to_rename(self):
        from unittest.mock import MagicMock

        from teamsleech.tg_bot.handlers.search_inputs import search_should_yield

        session = MagicMock()
        session.pending_rename_idx = 2
        session.date_input_pending = False
        assert search_should_yield(session) is True

    def test_yields_to_date_wizard(self):
        from unittest.mock import MagicMock

        from teamsleech.tg_bot.handlers.search_inputs import search_should_yield

        session = MagicMock()
        session.pending_rename_idx = None
        session.date_input_pending = True
        assert search_should_yield(session) is True

    def test_search_consumes_otherwise(self):
        from unittest.mock import MagicMock

        from teamsleech.tg_bot.handlers.search_inputs import search_should_yield

        session = MagicMock()
        session.pending_rename_idx = None
        session.date_input_pending = False
        assert search_should_yield(session) is False
