<div align="center">

# <img src="https://api.iconify.design/lucide:satellite-dish.svg?color=%238A2BE2" width="32" height="32" align="center" /> TeamsLeech Bot v2.x

> **An asynchronous Telegram Bot for discovering and mirroring Microsoft Teams academic recordings.**
> Built for students to eliminate manual downloads and save mobile data, running entirely on free cloud infrastructure with zero local intervention required.

</div>

---

## <img src="https://api.iconify.design/lucide:sparkles.svg?color=%238A2BE2" width="24" height="24" align="center" /> Features

- **Zero-Data Downloads**: Streams massive Teams recordings directly to Telegram servers without using your device's bandwidth or local storage.
- **Dynamic Discovery**: Automatically finds new recordings (and PDFs/Documents) even when you are added to new classes or groups mid-semester.
- **Interactive UI**: Manage your subjects, check for new recordings, and trigger uploads all via Telegram interactive menus.
- **Set & Forget**: Runs on a schedule via GitHub Actions. Token rotation happens silently, allowing it to run unattended for months.
- **Strictly Typed & Tested**: Modular architecture built on Python 3.11, Pydantic, HTTPX, and Pyrogram, with 100% async pipeline and CI/CD validation.

---

## <img src="https://api.iconify.design/lucide:git-pull-request.svg?color=%238A2BE2" width="24" height="24" align="center" /> Architecture

```text
       Telegram /check
              ↓
GitHub Actions (workflow_dispatch / cron)
              ↓
  OAuth2 refresh_token → access_token
  (auto-rotate via PyNaCl → GitHub Secrets)
              ↓
Graph API joinedTeams scan
  (httpx.AsyncClient · connection-pooled)
              ↓
  Filter by subject keywords & smart search
              ↓
 Find new .mp4 & .pdf files since last run
  (state stored as JSON document in Telegram pinned message)
              ↓
 Stream to Telegram Saved Messages
  (Pyrogram MTProto · chunked async generator)
```

---

## <img src="https://api.iconify.design/lucide:folder-tree.svg?color=%238A2BE2" width="24" height="24" align="center" /> Project Structure

```text
TeamsLeech-Bot/
├── src/teamsleech/
│   ├── core/                # Configuration and Pydantic BaseSettings
│   ├── models/              # Strictly-typed data contracts (domain.py)
│   ├── services/            # Core business logic:
│   │   ├── auth.py          # OAuth2 and GitHub Secrets rotation
│   │   ├── discovery.py     # Smart search engine for Teams
│   │   ├── graph.py         # 100% Async Microsoft Graph API client
│   │   ├── scanner.py       # Drive scanning & file filtering
│   │   ├── state.py         # Hybrid persistence (Telegram + memory)
│   │   └── transfer.py      # Async download-stream to MTProto upload
│   └── tg_bot/              # Presentation Layer:
│       ├── handlers/        # Command and callback routers
│       ├── keyboards.py     # Inline UI builders
│       └── views.py         # Text/Markdown formatters
├── tests/                   # Pytest unit tests for all modules
├── scripts/                 # Utility scripts (get_teams_token.py, etc.)
├── .github/workflows/       # CI/CD (Lint, Test, Semantic Release, Bot Runner)
├── pyproject.toml           # PEP 517 build, Hatchling, formatting config
└── README.md                # This file
```

---

## <img src="https://api.iconify.design/lucide:key.svg?color=%238A2BE2" width="24" height="24" align="center" /> Required GitHub Secrets

| Secret Name           | Description                                                   |
| --------------------- | ------------------------------------------------------------- |
| `TEAMS_REFRESH_TOKEN` | OAuth2 refresh token from `scripts/get_teams_token.py`.       |
| `GH_PAT`              | Personal Access Token with `secrets:write` permission.        |
| `TELEGRAM_API_ID`     | Telegram App API ID (from my.telegram.org).                   |
| `TELEGRAM_API_HASH`   | Telegram App API Hash (from my.telegram.org).                 |
| `TELEGRAM_BOT_TOKEN`  | Bot identity token (from @BotFather).                         |
| `TELEGRAM_CHAT_ID`    | Your personal Telegram numerical User ID.                     |
| `SUBJECTS_JSON`       | Managed automatically via the Telegram bot UI.                |

---

## <img src="https://api.iconify.design/lucide:rocket.svg?color=%238A2BE2" width="24" height="24" align="center" /> Local Development

To develop or test locally:
1. Clone the repository and navigate into it.
2. Install the project via `uv` or `pip`:
   ```bash
   pip install -e ".[dev]"
   ```
3. Copy `.env.example` to `.env` and fill in the secrets.
4. Run the CI suite to verify:
   ```bash
   ruff check .
   ruff format .
   mypy .
   pytest tests/
   ```

---

## <img src="https://api.iconify.design/lucide:file-text.svg?color=%238A2BE2" width="24" height="24" align="center" /> License

Built for **personal use only**. This tool is not licensed for commercial redistribution or SaaS operation.
