<div align="center">

# <img src="https://api.iconify.design/lucide:satellite-dish.svg?color=%238A2BE2" width="32" height="32" align="center" /> TeamsLeech Bot

> **A personal automation tool that monitors Microsoft Teams for new lecture recordings and streams them directly into Telegram Saved Messages.**
> Built for students to eliminate manual downloads and save mobile data, running entirely on free cloud infrastructure with zero local intervention required.

</div>

---

## <img src="https://api.iconify.design/lucide:sparkles.svg?color=%238A2BE2" width="24" height="24" align="center" /> What It Does

- **Zero-Data Downloads**: Streams massive Teams recordings directly to Telegram servers without using your device's bandwidth or local storage.
- **Dynamic Discovery**: Automatically finds new recordings even when you are added to new classes or groups mid-semester.
- **Set & Forget**: Runs on a schedule via GitHub Actions. Token rotation happens silently, allowing it to run unattended for months.
- **Telegram Interface**: Provides a simple UI within Telegram to check specific subjects and select which new recordings to capture.

---

## <img src="https://api.iconify.design/lucide:git-pull-request.svg?color=%238A2BE2" width="24" height="24" align="center" /> Architecture

```text
       Telegram /check
              ↓
GitHub Actions (workflow_dispatch)
              ↓
  OAuth2 refresh_token → access_token
              ↓
Graph API joinedTeams scan (98 teams)
              ↓
    Filter by 6 subject keywords
              ↓
 Find new .mp4 files since last run
              ↓
 Stream to Telegram Saved Messages
              ↓
Rotate refresh_token → GitHub Secret
```

---

## <img src="https://api.iconify.design/lucide:folder-tree.svg?color=%238A2BE2" width="24" height="24" align="center" /> Project Structure

```text
TeamsLeech-Bot/
├── src/
│   ├── main.py            # Orchestrator
│   ├── token_manager.py   # OAuth2 auth + token rotation
│   ├── fetcher.py         # Teams drive scanner
│   ├── bot.py             # Telegram UI + commands
│   └── uploader.py        # Video streamer
├── .github/
│   └── workflows/
│       └── workflow.yml   # GitHub Actions pipeline
├── docs/
│   └── PRD.md             # Product Requirements Document
├── tasks.md               # Project milestones
├── subjects_config.json   # 6 subjects + keyword arrays
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

---

## <img src="https://api.iconify.design/lucide:cpu.svg?color=%238A2BE2" width="24" height="24" align="center" /> Tech Stack

| Layer                 | Technology                           |
| --------------------- | ------------------------------------ |
| **Language**          | Python 3.11                          |
| **Authentication**    | MS Graph OAuth2 (refresh_token flow) |
| **Token Encryption**  | PyNaCl (libsodium)                   |
| **Telegram Client**   | Pyrogram + TgCrypto                  |
| **CI/CD Runner**      | GitHub Actions (ubuntu-latest)       |
| **Secrets Engine**    | GitHub Encrypted Secrets             |
| **State Persistence** | GitHub Actions Artifacts             |

---

## <img src="https://api.iconify.design/lucide:key.svg?color=%238A2BE2" width="24" height="24" align="center" /> Required GitHub Secrets

| Secret Name           | Description                                               |
| --------------------- | --------------------------------------------------------- |
| `TEAMS_REFRESH_TOKEN` | Initial OAuth2 refresh token from a manual browser login. |
| `GH_PAT`              | Personal Access Token with `secrets:write` permission.    |
| `TELEGRAM_API_ID`     | Telegram App API ID (from my.telegram.org).               |
| `TELEGRAM_API_HASH`   | Telegram App API Hash (from my.telegram.org).             |
| `TELEGRAM_BOT_TOKEN`  | Bot identity token (from @BotFather).                     |
| `TELEGRAM_CHAT_ID`    | Your personal Telegram numerical User ID.                 |

---

## <img src="https://api.iconify.design/lucide:rocket.svg?color=%238A2BE2" width="24" height="24" align="center" /> Setup

To deploy this project for your own university account:

1. **Fork** this repository.
2. **Capture initial `refresh_token`** by running `python scripts/get_teams_token.py` locally and following the Microsoft Device Login instructions.
3. **Add all 6 GitHub Secrets** listed above to your forked repository.
4. **Edit `subjects_config.json`** to define your own required subjects and their search keywords.
5. **Run the workflow** manually via the Actions tab → Select "TeamsLeech Bot" → Click "Run workflow".

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

---

## <img src="https://api.iconify.design/lucide:alert-triangle.svg?color=%238A2BE2" width="24" height="24" align="center" /> Limitations & Non-Goals

- **Strictly Single-User**: This is NOT a multi-user SaaS. It relies on a single user's credentials and operates exclusively for that account.
- **Fixed Subject Scope**: The bot only scans for the exact domains/keywords defined in the config. It will ignore other teams, even if you are a member.
- **Explicit Triggers Only**: It does not listen for real-time video uploads. It only checks Teams when you manually run the workflow or use the Telegram `/check` command.
- **No Video Processing**: Files are passed through exactly as they were uploaded to Teams. No transcription, compression, or format conversion occurs.
- **IT Independence**: Designed to work entirely with standard student privileges. It does not require Admin Azure AD app registration.

---

## <img src="https://api.iconify.design/lucide:file-text.svg?color=%238A2BE2" width="24" height="24" align="center" /> License

Built for **personal use only**. This tool is not licensed for commercial redistribution or SaaS operation.
