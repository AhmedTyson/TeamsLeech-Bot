# Contributing to TeamsLeech Bot

Thank you for your interest in contributing! This guide will help you get set up and productive quickly.

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/TeamsLeech-Bot.git
cd TeamsLeech-Bot
```

### 2. Create a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
# Edit .env and fill in your real values (see README.md for details)
```

## Project Structure

| File / Directory | Purpose |
|---|---|
| `src/main.py` | Orchestrator — wires all modules and starts the bot |
| `src/token_manager.py` | OAuth2 token exchange and GitHub secret rotation |
| `src/fetcher.py` | Microsoft Graph API scanner for Teams recordings |
| `src/bot.py` | Telegram bot interface (Pyrogram handlers) |
| `src/uploader.py` | Streams recordings from Graph to Telegram |
| `src/state_manager.py` | Persists per-subject timestamps via Telegram |
| `src/constants.py` | Shared constants (API URLs) |
| `scripts/` | One-time setup utilities |
| `tests/` | Manual verification scripts |
| `docs/` | GitHub Pages dashboard |
| `.github/workflows/` | GitHub Actions workflow definition |

## Running Locally

```bash
python src/main.py
```

The bot will start polling Telegram. Use `/start` in your Telegram chat to interact.

## Running via GitHub Actions

1. Push your code to GitHub
2. Set all secrets in Settings → Secrets and variables → Actions
3. Go to Actions → TeamsLeech Bot → Run workflow

## Style Guide

- **Python version**: 3.11+
- **Formatting**: Follow PEP 8
- **Imports**: Standard library → third-party → local (separated by blank lines)
- **Type annotations**: Required on all public function signatures
- **Docstrings**: Module-level docstrings are mandatory, follow NumPy-style
- **Logging**: Use `logging.getLogger(__name__)` — no `print()` in `src/` modules
- **Error handling**: Always catch specific exceptions, never bare `except:`

## Adding a New Subject

1. Open `subjects_config.json`
2. Add a new entry following the existing pattern:
   ```json
   {
     "name": "NewSubjectName",
     "keywords": ["keyword1", "keyword2"]
   }
   ```
3. The fetcher will automatically include it in the next scan

## Pull Request Guidelines

1. Keep PRs focused — one feature or fix per PR
2. Update docstrings if you change public API signatures
3. Do not commit `.env` or any real credentials
4. Test locally before opening a PR
