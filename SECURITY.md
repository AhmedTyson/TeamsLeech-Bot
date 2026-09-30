# Security Policy

## Secrets Inventory

TeamsLeech Bot uses the following secrets in production:

| Secret | Where Set | Scope | Rotation |
|---|---|---|---|
| `TEAMS_REFRESH_TOKEN` | GitHub Secrets | Microsoft Graph offline access | Auto-rotated by `services/auth.py` every run |
| `GH_PAT` | GitHub Secrets | Fine-grained PAT, this repo only, `secrets:write` (contents:read) | Manual — rotate at least every 90 days via GitHub Settings |
| `TELEGRAM_API_ID` | GitHub Secrets | Telegram API access | Static — from my.telegram.org |
| `TELEGRAM_API_HASH` | GitHub Secrets | Telegram API access | Static — from my.telegram.org |
| `TELEGRAM_BOT_TOKEN` | GitHub Secrets | Telegram Bot API | Manual — rotate via @BotFather |
| `TELEGRAM_CHAT_ID` | GitHub Secrets | Target Telegram chat | Static |
| `GIST_ID` | `docs/index.html` | Dashboard state gist | Static |
| `GIST_READ_TOKEN` | `docs/index.html` | GitHub Gist read-only PAT | Manual — rotate via GitHub Settings |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please **do not open a public issue**.

Instead, contact the maintainer directly:
- Email the repository owner (check the GitHub profile)
- Or open a private security advisory via GitHub (Settings → Security → Advisories)

## Token Exposure Impact

### TEAMS_REFRESH_TOKEN
**Risk**: High. Grants access to your Microsoft 365 account via the Graph API.
**Mitigation**: Auto-rotated every workflow run. If compromised, revoke all refresh tokens from [Microsoft account security](https://account.live.com/activity).

### GH_PAT
**Risk**: High. Can read/write repository secrets.
**Mitigation**: Use a fine-grained PAT limited to this repository with `secrets:write` (and `contents:read` for releases) — never a classic `repo`-scoped token. Rotate at least every 90 days. If `GH_PAT`/`GITHUB_REPOSITORY` is missing, `rotate_github_secret` now raises `SecretRotationError` loudly instead of skipping silently; callers log an error and keep the fresh token in-process only, so update the secret before the next restart.

### GIST_READ_TOKEN
**Risk**: Low. Read-only access to a single public/secret gist containing encrypted state.
**Mitigation**: Use a fine-grained PAT with `gist:read` scope only.

### TELEGRAM_BOT_TOKEN
**Risk**: Medium. Can send messages and access bot conversations.
**Mitigation**: Revoke and regenerate via @BotFather if compromised.

### TELEGRAM_SESSION_STRING
**Risk**: High. Full user-account access (uploads up to 2 GB, bypasses the 50 MB bot cap).
**Mitigation**: Mint locally via `python scripts/get_telegram_session.py`, store only as a GitHub Secret, never commit or paste it. Optional — without it, files above 50 MB fail with a clear error instead of uploading.

## Best Practices

1. **Never commit `.env`** — it is listed in `.gitignore`
2. **Use GitHub Secrets** for all production credentials
3. **Rotate tokens** if you suspect any exposure
4. **Audit `docs/index.html`** before deploying — ensure `GIST_ID` and `GIST_READ_TOKEN` are your own, not someone else's
5. **Keep `GH_PAT` scoped tightly** — fine-grained PAT, this repo only, `secrets:write` (+ `contents:read` for releases)
