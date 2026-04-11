# Security Policy

## Secrets Inventory

TeamsLeech Bot uses the following secrets in production:

| Secret | Where Set | Scope | Rotation |
|---|---|---|---|
| `TEAMS_REFRESH_TOKEN` | GitHub Secrets | Microsoft Graph offline access | Auto-rotated by `token_manager.py` every run |
| `GH_PAT` | GitHub Secrets | `repo` scope (secrets:write) | Manual — rotate via GitHub Settings |
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
**Mitigation**: Use fine-grained PATs with minimum required scopes. Rotate regularly.

### GIST_READ_TOKEN
**Risk**: Low. Read-only access to a single public/secret gist containing encrypted state.
**Mitigation**: Use a fine-grained PAT with `gist:read` scope only.

### TELEGRAM_BOT_TOKEN
**Risk**: Medium. Can send messages and access bot conversations.
**Mitigation**: Revoke and regenerate via @BotFather if compromised.

## Best Practices

1. **Never commit `.env`** — it is listed in `.gitignore`
2. **Use GitHub Secrets** for all production credentials
3. **Rotate tokens** if you suspect any exposure
4. **Audit `docs/index.html`** before deploying — ensure `GIST_ID` and `GIST_READ_TOKEN` are your own, not someone else's
5. **Keep `GH_PAT` scoped tightly** — only `repo` and `secrets:write`
