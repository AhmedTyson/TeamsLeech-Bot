# Tech Stack

- **Language:** Python 3.11+
- **Telegram Client:** Pyrogram (async MTProto framework) + TgCrypto (for speed)
- **HTTP Client:** `httpx` (async) for Microsoft Graph API & GitHub API. `requests` was completely eliminated.
- **Validation:** `pydantic` & `pydantic-settings` (strict data contracts).
- **Environment:** GitHub Actions (`ubuntu-latest`).
- **Media Tools:** Requires `ffmpeg` and `ffprobe` in the system path for extracting video durations and thumbnails before Telegram upload.
- **Encryption:** `PyNaCl` (libsodium) specifically for encrypting Github Secrets directly from the bot.