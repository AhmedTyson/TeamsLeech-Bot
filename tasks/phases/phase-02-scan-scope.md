# Phase 2 — Scan harmony: 60-day default, no last-run (UI spec)

## Current UI (replace)
- `✅ Check All (since last run)` → scans since stored `last_run`.
- Subject tap → date prompt (`📅 Today` `📅 This Week` / `♾️ All Time`), typed dates capped at 30 days (error only after typing).
- Results header label: `Since Last Run`.

## New UI
Subject picker (`/check`):
```
**What do you want to check?**
[ DataSec ]  [ ForTrade ]
[ ✅ Check All (last 60 days) ]
```
- Tap subject → scope prompt (60 days is default-first):
  ```
  📚 **Data Security** — pick scope:
  [ 🗓 Last 60 Days ]   ← default, first
  [ 📅 Today ]  [ 📅 This Week ]
  [ ♾️ All Time ]
  Or type: 2026-04-01 · 2026-04-01 to 2026-05-15 · march 2026
  _Ranges up to 60 days._
  ```
- Tap `✅ Check All` → scans immediately, no prompt: `🔍 Scanning **all subjects** — Last 60 Days...`
- Cap raised 30 → 60 days; prompt states it upfront.
- Results header: `📅 Last 60 Days · 2 teams` (label + team count, never "Since Last Run").
- Scheduled auto-check label: `Last 60 Days`.

## Flow
1. `scan_recordings`: drop `last_run`/`ignore_last_run`; no-date → `date_start = today-60d, date_end = today`.
2. `scanner_ui`: new `scope:60d` button path; `date_btn:all` unchanged mechanic (now truly all).
3. State writes (`save_last_run`/`save_last_lecture`) kept; all reads-as-filter deleted.
4. `MAX_DATE_RANGE_DAYS` 30 → 60.

## Edge cases
- Recording older than 60 days + no scope → excluded by date, message says scope (`Last 60 Days`), not "no new files" mystery.
- `All Time` on huge libraries: truncation note already exists in `views.py`; keep.

## Acceptance
- [ ] No-date scan includes 30-day-old file, excludes 61-day-old file (unit)
- [ ] No `get_last_run`-as-filter call remains (grep)
- [ ] Live: Check All lists 60-day window with correct label
