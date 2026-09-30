"""Smoke: package imports and handler registration without network."""


def test_core_imports():
    import teamsleech.core.config
    import teamsleech.core.constants
    import teamsleech.core.retry
    import teamsleech.models.domain
    import teamsleech.services.auth
    import teamsleech.services.discovery
    import teamsleech.services.github_actions
    import teamsleech.services.github_secrets
    import teamsleech.services.graph
    import teamsleech.services.scanner
    import teamsleech.services.state
    import teamsleech.services.transfer
    import teamsleech.tg_bot.callbacks
    import teamsleech.tg_bot.filters
    import teamsleech.tg_bot.handlers
    import teamsleech.tg_bot.keyboards
    import teamsleech.tg_bot.views

    assert teamsleech.core.config.settings is not None


def test_handler_registration_wires_all():
    from unittest.mock import MagicMock

    from teamsleech.tg_bot.handlers import register_all_handlers

    app = MagicMock()
    registered = []

    def _capture(*args, **kwargs):
        def wrap(func):
            registered.append(func.__name__)
            return func

        return wrap

    app.on_callback_query.side_effect = _capture
    app.on_message.side_effect = _capture
    register_all_handlers(app, MagicMock(), MagicMock(), MagicMock(), MagicMock())

    assert "handle_upload" in registered
    assert "handle_search_input" in registered
    assert "handle_date_input" in registered
