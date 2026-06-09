# TeamsLeech Bot - Core Architecture

This project is a high-performance, asynchronous Telegram Bot designed to fetch and stream Microsoft Teams academic recordings and documents directly to Telegram.

## Architecture Layout
- **src/main.py**: The entry point. Handles DI (Dependency Injection), initializes services, authenticates, registers Telegram handlers, and starts polling. Also handles the silent auto-check triggered by GitHub Actions CRON.
- **src/core/**: `config.py` (Pydantic `AppConfig` validating environment variables on boot) and `constants.py`.
- **src/models/domain.py**: Strict Pydantic models mapping the entire domain (`Recording`, `SubjectConfig`, `Team`, `UserSession`).
- **src/services/**: Pure Business Logic. 
  - `auth.py`: Token exchange & GitHub Secrets rotation using libsodium via GitHub API.
  - `graph.py`: 100% async Microsoft Graph wrapper (`GraphClient`) utilizing `httpx` connection pools and pagination.
  - `discovery.py`: Searches joined Teams via Graph API and maps to `Team` models.
  - `scanner.py`: Searches Graph drives concurrently for `.mp4`, `.pdf`, `.pptx`, `.docx`, etc.
  - `transfer.py`: Pipes data stream from Graph API tempfile -> Telegram via Pyrogram.
  - `state.py`: Hybrid persistence model. Ephemeral FSM state (`UserSession`) saved in memory. Persistent data (`last_run` timestamps) synced via a JSON string to a pinned Telegram message.
- **src/tg_bot/**: Presentation Layer.
  - `views.py`: Markdown formatters and icons.
  - `keyboards.py`: InlineKeyboardMarkup buttons.
  - `filters.py`: Auth checks (`owner_only`).
  - `handlers/`: Modular routing replacing god-files. Contains `commands.py`, `scanner_ui.py`, `search_inputs.py`, and `upload_ui.py`.

## Infrastructure
Deployed as a GitHub Action. The runner uses `ubuntu-latest`. It pulls the `SUBJECTS_JSON` and `TEAMS_REFRESH_TOKEN` dynamically. The `search_inputs.py` module allows interactive updating of the config via Telegram, which atomically overwrites the GitHub Secrets.