<div align="center">

# <img src="https://api.iconify.design/lucide:satellite-dish.svg?color=%238A2BE2" width="32" height="32" align="center" /> TeamsLeech Bot

> **A personal automation tool that monitors Microsoft Teams for new lecture recordings and streams them directly into Telegram Saved Messages.**
> Built for students to eliminate manual downloads and save mobile data, running entirely on free cloud infrastructure with zero local intervention required.

[![Complete Guide](https://img.shields.io/badge/📖_Complete_Guide-Read_Now-8A2BE2?style=for-the-badge)](docs/TeamsLeech_Guide.md)

</div>

---

## <img src="https://api.iconify.design/lucide:book-open.svg?color=%238A2BE2" width="24" height="24" align="center" /> Documentation

**New here?** Start with the **[Complete Guide](docs/TeamsLeech_Guide.md)** — a comprehensive walkthrough covering architecture, setup, usage, security, troubleshooting, and lessons learned. It is written for both developers who want to understand the system and beginners who want to deploy it for their own university.

---

## <img src="https://api.iconify.design/lucide:sparkles.svg?color=%238A2BE2" width="24" height="24" align="center" /> What It Does

- **Zero-Data Downloads**: Streams massive Teams recordings directly to Telegram servers without using your device's bandwidth or local storage.
- **Dynamic Discovery**: Automatically finds new recordings even when you are added to new classes or groups mid-semester.
- **Set & Forget**: Runs on a schedule via GitHub Actions. Token rotation happens silently, allowing it to run unattended for months.
- **Telegram Interface**: Provides a simple UI within Telegram to check specific subjects and select which new recordings to capture.
- **Web Dashboard**: Optional control panel served via GitHub Pages with biometric unlock, live step tracking, and workflow dispatch.

---

## <img src="https://api.iconify.design/lucide:git-pull-request.svg?color=%238A2BE2" width="24" height="24" align="center" /> Architecture

```text
       Telegram /check  ·  Dashboard dispatch
              ↓
GitHub Actions (workflow_dispatch)
              ↓
  OAuth2 refresh_token → access_token
  (auto-rotate via PyNaCl → GitHub Secrets)
              ↓
Graph API joinedTeams scan (98 teams)
  (httpx.AsyncClient · asyncio.gather · cap 20)
              ↓
    Filter by subject keywords
              ↓
 Find new .mp4 files since last run
  (per-subject timestamps from Telegram pinned message)
              ↓
 Stream to Telegram Saved Messages
  (Pyrogram MTProto · send_video · ffprobe metadata)
```

> For a deep architectural walkthrough of each module, see the **[Architecture Deep-Dive](docs/TeamsLeech_Guide.md#4-architecture-deep-dive)** in the Complete Guide.

---

## <img src="https://api.iconify.design/lucide:folder-tree.svg?color=%238A2BE2" width="24" height="24" align="center" /> Project Structure

```text
TeamsLeech-Bot/
├── src/
│   ├── main.py              # Orchestrator — wires all modules together
│   ├── token_manager.py     # OAuth2 auth + PyNaCl token rotation
│   ├── fetcher.py           # Async Teams drive scanner (httpx + asyncio)
│   ├── bot.py               # Telegram UI — keyboards, checklists, rename
│   ├── uploader.py          # Graph download → ffprobe → MTProto upload
│   ├── state_manager.py     # Pinned Telegram message state persistence
│   └── constants.py         # Shared constants
├── scripts/
│   ├── get_teams_token.py   # OAuth2 device login flow
│   ├── generate_session.py  # Pyrogram session string generator
│   └── setup_gist.py       # Dashboard credential encryption setup
├── docs/
│   ├── TeamsLeech_Guide.md  # 📖 The Complete Guide (start here)
│   ├── index.html           # Web dashboard (GitHub Pages)
│   └── PRD.md               # Product Requirements Document
├── .github/
│   └── workflows/
│       └── workflow.yml     # GitHub Actions pipeline
├── subjects_config.json     # Subject names + keyword arrays
├── requirements.txt         # Python dependencies
├── CONTRIBUTING.md          # Contribution guidelines
├── SECURITY.md              # Security policy & disclosure
└── README.md                # This file
```

---

## <img src="https://api.iconify.design/lucide:cpu.svg?color=%238A2BE2" width="24" height="24" align="center" /> Tech Stack

| Layer                 | Technology                                   |
| --------------------- | -------------------------------------------- |
| **Language**          | Python 3.11                                  |
| **Authentication**    | MS Graph OAuth2 (refresh_token flow)         |
| **Token Encryption**  | PyNaCl (libsodium sealed box)                |
| **Telegram Client**   | Pyrogram + TgCrypto (MTProto)                |
| **HTTP Client**       | httpx (async, connection-pooled)             |
| **CI/CD Runner**      | GitHub Actions (ubuntu-latest, free tier)    |
| **Secrets Engine**    | GitHub Encrypted Secrets                     |
| **State Persistence** | Telegram Pinned Message (JSON key-value)     |
| **Dashboard**         | Static HTML + Web Crypto API + GitHub Pages  |

---

## <img src="https://api.iconify.design/lucide:key.svg?color=%238A2BE2" width="24" height="24" align="center" /> Required GitHub Secrets

| Secret Name           | Description                                                   |
| --------------------- | ------------------------------------------------------------- |
| `TEAMS_REFRESH_TOKEN` | OAuth2 refresh token from `scripts/get_teams_token.py`.       |
| `TELEGRAM_SESSION`    | Pyrogram session string from `scripts/generate_session.py`.   |
| `GH_PAT`              | Personal Access Token with `secrets:write` permission.        |
| `TELEGRAM_API_ID`     | Telegram App API ID (from my.telegram.org).                   |
| `TELEGRAM_API_HASH`   | Telegram App API Hash (from my.telegram.org).                 |
| `TELEGRAM_BOT_TOKEN`  | Bot identity token (from @BotFather).                         |
| `TELEGRAM_CHAT_ID`    | Your personal Telegram numerical User ID.                     |
| `SUBJECTS_JSON`       | *(Optional)* Subject config JSON — overrides `subjects_config.json`. |

> For detailed instructions on obtaining each credential, see the **[Full Setup Walkthrough](docs/TeamsLeech_Guide.md#6-full-setup-walkthrough)** in the Complete Guide.

---

## <img src="https://api.iconify.design/lucide:rocket.svg?color=%238A2BE2" width="24" height="24" align="center" /> Quick Start

> **For the full step-by-step setup with screenshots and explanations, read the [Complete Guide](docs/TeamsLeech_Guide.md#6-full-setup-walkthrough).**

1. **Fork** this repository.
2. **Capture initial `refresh_token`** by running `python scripts/get_teams_token.py` locally and following the Microsoft Device Login instructions.
3. **Generate Telegram session** by running `python scripts/generate_session.py` and completing the login flow.
4. **Add all GitHub Secrets** listed above to your forked repository.
5. **Edit `subjects_config.json`** to define your own subjects and their search keywords.
6. **Run the workflow** manually via the Actions tab → Select "TeamsLeech Bot" → Click "Run workflow".
7. *(Optional)* **Deploy the dashboard** — see [Step 6 in the guide](docs/TeamsLeech_Guide.md#66-step-6--deploy-the-dashboard).

---

## <img src="https://api.iconify.design/lucide:bar-chart-2.svg?color=%238A2BE2" width="24" height="24" align="center" /> Confirmed Performance

| Metric                | Value                           |
| --------------------- | ------------------------------- |
| Teams scanned per run | 98                              |
| Download speed        | ~148MB in 5s (Azure datacenter) |
| Upload speed          | ~238MB in 7s                    |
| Avg run duration      | ~8 minutes                      |
| Monthly Actions usage | ~200 min / 2000 free            |
| Infrastructure cost   | $0                              |
| Run success rate      | 93%                             |

---

## <img src="https://api.iconify.design/lucide:alert-triangle.svg?color=%238A2BE2" width="24" height="24" align="center" /> Limitations & Non-Goals

- **Strictly Single-User**: This is NOT a multi-user SaaS. It relies on a single user's credentials and operates exclusively for that account.
- **Fixed Subject Scope**: The bot only scans for the exact domains/keywords defined in the config. It will ignore other teams, even if you are a member.
- **Explicit Triggers Only**: It does not listen for real-time video uploads. It only checks Teams when you manually run the workflow or use the Telegram `/check` command.
- **No Video Processing**: Files are passed through exactly as they were uploaded to Teams. No transcription, compression, or format conversion occurs.
- **IT Independence**: Designed to work entirely with standard student privileges. It does not require Admin Azure AD app registration.

---

## <img src="https://api.iconify.design/lucide:users.svg?color=%238A2BE2" width="24" height="24" align="center" /> Contributing

Contributions are welcome! Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before submitting a pull request. For security-related issues, follow the process in [`SECURITY.md`](SECURITY.md).

---

## <img src="https://api.iconify.design/lucide:file-text.svg?color=%238A2BE2" width="24" height="24" align="center" /> License

Built for **personal use only**. This tool is not licensed for commercial redistribution or SaaS operation.
