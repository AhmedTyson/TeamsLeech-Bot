# Phase 8 — Copy polish (before → after table)

Apply after Phases 2/5/7 behaviors are final. Voice: short, plain, no stale claims.

| Location | Before | After |
|---|---|---|
| `/start` quick access | "Tap a subject → scans this week automatically" | "Tap a subject → pick scope (60 days default)" |
| `/check` tip | date-only tip | + `Scope defaults to last 60 days.` |
| Scope prompt | (new in P2) | `Ranges up to 60 days.` stated upfront |
| 30-day violation | `❌ Date range cannot exceed 30 days.` | `❌ Max range is 60 days — split it or tap ♾️.` |
| Empty results | `✅ No new files found.` | `✅ Nothing in <Scope> for <subjects>.` |
| Checklist footer | `Select to upload:` | `Tap numbers to select, then 🚀 Upload.` |
| `/runner` | panel | removal notice (P1) |
| Upload start | `Uploading N file(s)...` | `☁️ Uploading N file(s)…` + live `📊` (P7) |
| Secret failures | `Make sure your GH_PAT is valid.` | keep (accurate) |
| Cookie expiry | re-export hint (exists) | keep + point to `docs/cookie-download.md` once |

## Rules
- Every user-facing string touched gets its unit test updated in the same edit.
- No new features; strings only (plus the `/start` keyboard row from P1/P6).

## Acceptance
- [ ] Grep review of all reply/edit strings by human
- [ ] Suite green
