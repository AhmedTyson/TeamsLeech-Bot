# Todo: UI overhaul — 10 phases (ordered)

> UI detail specs live in `tasks/phases/phase-01…10`. Each phase file has exact
> texts, button layouts, flows, and edge cases — the task below is the checklist.

## Phase 1: Delete Background Runner feature

**Description:** Remove runner management: `/runner` command, `⚙️ Background Runner` reply-keyboard button, actions panel (trigger/status), keeping only what Phase 6 re-adds. Delete `actions_ui.py`, `github_actions.py` usages, keyboards, tests.

**Acceptance criteria:**
- [x] No `/runner`, no `⚙️` button, no `act:*` callbacks, no trigger/status code paths
- [x] `test_run.py` removed or repurposed (no dead references)
- [x] Full suite green

**Verification:**
- [x] `pytest tests/unit -q` passes
- [x] `ruff check src/ tests/` clean
- [x] Grep shows no `act:run`, `act:status`, `trigger_workflow` references

**Dependencies:** None

**Files likely touched:**
- `src/teamsleech/tg_bot/handlers/actions_ui.py` (delete)
- `src/teamsleech/services/github_actions.py` (delete or trim to cancel-only — see Phase 6)
- `src/teamsleech/tg_bot/keyboards.py`, `handlers/__init__.py`, `handlers/commands.py`
- `test_run.py`, `tests/unit/test_actions_ui.py`, `tests/unit/test_github_actions.py`

**Estimated scope:** Medium (5+ files, mostly deletions)

## Checkpoint: After Phase 1
- [ ] Tests pass, bot boots, `/start` keyboard has no runner button

## Phase 2: Scan harmony — 60-day default, no last-run filter

**Description:** Delete last-run filtering everywhere: every scan covers all joined teams over the last 60 days unless the user gives scope (today / this week / custom range / All Time). State (`last_run`, `last_lecture`) stays as knowledge only — written, never read as a filter. Remove `ignore_last_run`, `subj:__ALL__` "since last run" semantics, auto-check label.

**Acceptance criteria:**
- [x] No code path drops a recording because of stored `last_run`
- [x] No-date scan = `today - 60d` … today on every team
- [x] Explicit dates / All Time still work; 30-day cap revisited (raise to 60+ or drop)
- [x] State still records `last_run`/`last_lecture` per subject (knowledge only)

**Verification:**
- [x] New/updated `test_scanner.py`: old recording included with no dates; 61-day-old excluded by default; explicit range overrides
- [ ] Full suite green; live `/check` shows 60-day label

**Dependencies:** Phase 1

**Files likely touched:**
- `src/teamsleech/services/scanner.py`
- `src/teamsleech/tg_bot/handlers/scanner_ui.py`, `main.py` (auto-check)
- `tests/unit/test_scanner.py`, `tests/unit/test_scanner_ui.py`

**Estimated scope:** Medium (3–5 files)

## Phase 3: Doctor + subject matching model

**Description:** Fix cross-doctor bleed: matching becomes AND — team must match subject keywords AND (when set) doctor keywords. Extend `SubjectConfig` with `doctor_keywords: list[str]` (keep `doctor` label for rename suggestions). Either list may be empty (optional), mirroring Phase 4 validation (≥1 required at creation).

**Acceptance criteria:**
- [x] Team matching wrong doctor but right subject is excluded when `doctor_keywords` set
- [x] Empty `doctor_keywords` = old behavior (subject-only); empty subject keywords + doctor set = doctor-only
- [x] Old secrets without `doctor_keywords` load fine (default `[]`, pydantic `extra=ignore` already)

**Verification:**
- [x] `test_scanner.py` `_match_teams` cases: both-match, subject-only, doctor-only, cross-doctor excluded
- [x] Migration check: existing `SUBJECTS_JSON` loads unchanged

**Dependencies:** Phase 2

**Files likely touched:**
- `src/teamsleech/models/domain.py`
- `src/teamsleech/services/scanner.py`
- `tests/unit/test_scanner.py`, `tests/unit/test_domain.py`

**Estimated scope:** Small (2–3 files)

## Checkpoint: After Phases 2–3
- [ ] Scan returns 60-day all-teams results, correctly split by doctor+subject
- [ ] Live check on one subject verified by human

## Phase 4: Add flow collects subject + doctor

**Description:** Rework subject setup: after picking a team, ask for subject keywords AND doctor keywords (each skippable via `skip`, but at least one required — reject empty/empty). Store both lists; keep name/short/doctor-label steps.

**Acceptance criteria:**
- [x] `skip`/`skip` rejected with re-prompt; any other combo accepted
- [x] Saved `SUBJECTS_JSON` contains both keyword lists
- [x] `cancel` works at every step

**Verification:**
- [x] Handler tests cover skip/skip, subject-only, doctor-only, both, cancel-midway
- [ ] Live add of one subject verified

**Dependencies:** Phase 3

**Files likely touched:**
- `src/teamsleech/tg_bot/handlers/search_inputs.py`
- `tests/unit/` new or extended search-input tests

**Estimated scope:** Medium (2–3 files + tests)

## Phase 5: Numbered manage UI with edit

**Description:** Replace per-subject `❌ Delete X` button wall with a numbered list (same style as scan results). User taps/selects a number → gets `✏️ Edit` / `❌ Delete` for that entry. Edit walks name → short → doctor label → subject keywords → doctor keywords (each keepable via `skip`/empty = keep current), then saves to `SUBJECTS_JSON` secret like add/delete do.

**Acceptance criteria:**
- [x] Management message lists subjects numbered; selection by number buttons (paginated if long)
- [x] Edit updates chosen fields, keeps rest, persists to secret + runtime settings
- [x] Delete keeps current behavior via the same number flow

**Verification:**
- [x] Handler tests: select → edit doctor only; select → delete; invalid number handled
- [ ] Live edit + delete verified

**Dependencies:** Phases 3–4

**Files likely touched:**
- `src/teamsleech/tg_bot/handlers/commands.py` (dashboard text)
- `src/teamsleech/tg_bot/handlers/search_inputs.py` (select/edit/delete flows)
- `src/teamsleech/tg_bot/keyboards.py`, `views.py` (numbered management render)

**Estimated scope:** Medium (4–5 files)

## Checkpoint: After Phases 4–5
- [ ] Add → scan → manage → edit → delete full loop works live end-to-end

## Phase 6: Cancel-only workflow button

**Description:** Single `🛑 Cancel Workflow` button (reply keyboard, replacing the removed runner row) that cancels active `bot-runner` runs via kept `cancel_run`/`get_active_runs` helpers. No trigger, no status panel.

**Acceptance criteria:**
- [x] One button, one action: cancels active runs, reports count or "idle"
- [x] No trigger/status code resurrected

**Verification:**
- [x] Unit test with mocked runs (2 active → "cancelled 2"; none → idle message)
- [ ] Live cancel verified

**Dependencies:** Phase 1

**Files likely touched:**
- `src/teamsleech/services/github_actions.py` (trim to cancel + list)
- `src/teamsleech/tg_bot/keyboards.py`, `handlers/commands.py` (+ new tiny handler or reuse)
- `tests/unit/test_github_actions.py`

**Estimated scope:** Small (2–3 files)

## Phase 7: Fix progress visibility

**Description:** Investigate first (repro: multi-file upload, watch chat): current `file_progress` fires only on multiples of 5% and shares an edited message with completion lines — easy to miss. Then fix: guaranteed visible per-file download % + upload state in ONE live message (e.g. `⬇️ 45% name` → `⬆️ sending name` → `✅ name`), failures already standalone (keep), final summary kept.

**Acceptance criteria:**
- [x] Root cause of "didn't see it" written down (throttling/edit-collision/overwrite)
- [ ] Every file shows download progress then upload state in the live message
- [x] No message spam (single progress message + standalone failures + summary)

**Verification:**
- [x] Unit test asserts callback sequence for a 2-file upload
- [ ] Live 2-file upload observed by human

**Dependencies:** Phase 2 (scan output feeds it)

**Files likely touched:**
- `src/teamsleech/services/transfer.py` (`_report_progress`, producer/consumer cadence)
- `src/teamsleech/tg_bot/handlers/upload_ui.py` (progress message render)
- `tests/unit/test_transfer.py`

**Estimated scope:** Medium (2–3 files)

## Checkpoint: After Phases 6–7
- [ ] Cancel button + visible progress verified live

## Phase 8: Copy polish

**Description:** Consistent tone + truthful help: fix `/start` text (no auto-this-week claim), state the active scope rule (60 days default) wherever dates are asked, unify empty-state/error phrasing, document cookie-expiry + reauth in one `/help`-style text if cheap.

**Acceptance criteria:**
- [x] No stale claims about last-run/this-week behavior anywhere
- [x] Scope rule + 30/60-day cap stated before input, not after violation
- [x] Consistent emoji/voice pass over touched messages

**Verification:**
- [ ] Grep review of user-facing strings by human
- [x] Unit tests updated where they assert old copy

**Dependencies:** Phases 2, 5, 7 (copy depends on final behaviors)

**Files likely touched:**
- `src/teamsleech/tg_bot/handlers/commands.py`, `scanner_ui.py`, `upload_ui.py`, `search_inputs.py`
- `src/teamsleech/tg_bot/views.py`

**Estimated scope:** Small (scattered strings + test updates)

## Phase 9: Rename-button friction research

**Description:** Research-only first: can per-item `✏️` buttons go without hurting the common select flow? Options: (a) tap toggles, long-press/double-tap renames (Telegram has no long-press callbacks — likely dead); (b) select-then-rename mode button (`✏️ Rename mode` toggles buttons into rename targets); (c) keep as-is. Spike (b) behind nothing (small change) only if research favors it.

**Acceptance criteria:**
- [ ] Decision written: keep / mode-toggle / other, with Telegram-limits justification
- [ ] If change: button count per item drops in default view

**Verification:**
- [ ] Human approves decision before any edit
- [ ] If changed: existing toggle tests still green + new mode tests

**Dependencies:** Phase 8

**Files likely touched (if changed):**
- `src/teamsleech/tg_bot/keyboards.py`, `handlers/upload_ui.py`

**Estimated scope:** XS research (Small if changed)

## Checkpoint: After Phases 8–9
- [ ] Copy + rename decisions reviewed with human

## Phase 10: Full-text buttons research (last)

**Description:** Research-only first, adopted only if viable: can toggle buttons carry full recording text without hiding actions? Check current Telegram limits (button text length, 8-per-row / 100-button caps, wrapping behavior — numbers stay as fallback). Spike on one checklist if promising; otherwise document "numbers stay" with reasons and close.

**Acceptance criteria:**
- [ ] Measured limits documented (chars, rows, total) from live test or current docs
- [ ] Adopt full-text OR keep numbered toggles with explicit justification
- [ ] If adopted: actions (upload/filters/cancel) remain visible without scrolling on typical lists

**Verification:**
- [ ] Live checklist screenshot/review by human
- [ ] Full suite green either way

**Dependencies:** Phases 7–9

**Files likely touched (if changed):**
- `src/teamsleech/tg_bot/keyboards.py`, `views.py`, handler tests

**Estimated scope:** XS research (Medium if adopted)

## Checkpoint: Complete
- [ ] All 10 phases acceptance-checked
- [ ] Live end-to-end: add (doctor+subject) → 60-day scan → select → progress → deliver → manage/edit → cancel-button
- [ ] Ready for review

---

# Audit: search & keywords detection (ordered)

Source: live log 2026-10-03 18:48–19:01 + verify runs. Goal: every subject in
`SUBJECTS_JSON` grabs its teams' data; every mistake gets a fix.

## A1: Stale-code run judged as new behavior — PROCESS (no code)

**Finding:** 18:51–19:01 scans ran 60-day scope from the 18:48 boot (pre-fix
code). New code only took effect after the user-triggered fresh run
(`Scope: all time` lines + cancel of old run at 19:01).
**Fix:** always trigger a fresh `workflow_dispatch` after push before judging;
concurrency cancels the old runner — expected, not a bug.
**Status:** [x] documented

## A2: Zero-team subject (Dr. Abdelrahman Farmawy) — RESOLVED via gist rebuild

**Fix applied:** improved JSON (additive doctor part-splits + `Project 1` /
`Project` keywords) published to secret gist; `SUBJECTS_URL` secret set;
live verify `37154132870`: **9/9 subjects match exactly 1 team, zero
cross-bleed, zero config flags.** Gist is now the live source.

**Finding:** 0 teams in verify (twice) and in 3 live scans. User rewrote
`SUBJECTS_JSON` 4× blind (18:51–18:58 PUTs) with no feedback loop.
**Fix:** verify mode now prints `💡 maybe you meant:` closest team names
(`suggest_teams` token overlap). User picks correct keywords via manage UI.
**Verification:**
- [x] `test_suggest_teams` overlap/empty cases pass
- [ ] Live `mode=verify` shows suggestion for the Farmawy subject
- [ ] User fixes keywords; follow-up verify shows 1 team

**Files:** `services/scanner.py`, `main.py`, `tests/unit/test_scanner.py`

## A3: Spaceless team names vs natural keywords — FIXED

**Finding:** `Data Security` never matched `BIS-DataSecurity-…`.
**Fix:** punctuation-insensitive substring (`5d028af`) + `same` default in add
flow. **Status:** [x] shipped, unit-covered

## A4: Default scope filtered silently — FIXED

**Finding:** 60-day window + "Since Last Run" labels hid old files.
**Fix:** unbounded default, `All Recordings` labels (`5d028af`).
**Status:** [x] shipped, live log confirms `Scope: all time`

## A5: QUERY_ID_INVALID on slow/stale taps — FIXED

**Finding:** 18:59:54 traceback: `cb.answer()` after minutes-long scan.
**Fix:** answer-first (`safe_answer`) in Check-All + delete-confirm paths;
`safe_answer` helper never raises.
**Verification:**
- [x] Ruff + unit green
- [ ] Live: no dispatcher ERROR on slow scans

**Files:** `tg_bot/handlers/__init__.py`, `scanner_ui.py`, `search_inputs.py`

## A6: Per-subject grab audit — verify tally (live proof per subject)

**Method:** `mode=verify` prints, for EVERY subject: matched teams, then
`🎞 grabbed per subject: N 🎬 + M 📄 from <teams>`.
**Status:**
- [x] Implemented (`f169a2d`), live 18:43 run: 8 subjects grab (4+5, 1+0, 6+8…), 1 zero-team (→A2)
- [ ] Re-run verify after Farmawy keywords fixed; expect 9/9 grabbing

## A7: Keyword system rebuilt + validated live

**Rebuild (`b18430a`, 184 tests pass):**
- Matcher ignores <3-char keywords (`L4` matched every team before)
- Add/edit flows reject short/generic keywords with explicit messages
- Add flow self-check: keywords must match the picked team itself, else redo
- Verify flags invalid configs per subject (`⚠️ config: …`)

**Live verify `37150720855`:** zero `config:` flags across all 9 subjects —
every config is format-valid. The Farmawy zero-match is a wrong-team reference
(not a format problem): fix = pick the right team name from its `💡 maybe you
meant` list via manage UI edit.

## A8: Same-name subjects overwrote each other — FIXED (`5c67152`)

**Finding:** `results["Project 1"]` kept only the LAST doctor's list; the
doctors map did the same (both DS sections showed Hany; Soha's 2 files
vanished). Your "2 then 0" contradiction exactly.
**Fix:** results/results-maps/recordings keyed by unique short code;
duplicate shorts rejected at add/edit and flagged in verify.
**Live verify `37155281270`:** `DSS - Soha: 2 recordings` present; every
doctor on its own line with short code; zero cross-matches. 195 tests pass.

## Checkpoint: Audit complete
- [x] Team drives audited: ~22 .mp4, no truncation, no index gap (verify 19:26, 19:31)
- [x] No Recordings folders — files live in Documents roots (verify 19:31)
- [x] Own OneDrive: 404, not provisioned — nothing there (verify 19:36)
- [x] Conclusion: everything reachable with this session is grabbed; missing files live outside this account's reach (recorders' OneDrives, unjoined Teams)
- [ ] Farmawy keywords fixed by user → re-verify 9/9
- [ ] Ready for review

---

# Phase 11: Keyword audit + auto-repair (spec: tasks/phases/phase-11-keyword-audit-repair.md)

**Description:** Bot shows and fixes its own `SUBJECTS_JSON` (secret,
unreadable to humans): verify prints every subject's keywords + flags +
suggestions; new `mode=repair` safely ADDS missing team-name keywords and
re-saves; team search matches normalized text too.

**Acceptance criteria:**
- [ ] Verify lists all keyword lists + self-match status per subject
- [ ] Repair converts zero-match subjects to matched, never deletes user keywords
- [ ] Normalized team search finds spaceless names
- [ ] Full suite green + live verify/repair runs

**Verification:**
- [ ] Unit: audit flags, repair diff, normalized search
- [ ] Live `mode=verify` then `mode=repair` then verify again → 9/9 grabbing

**Dependencies:** A1–A7 done

**Files likely touched:**
- `src/teamsleech/main.py` (verify report + repair mode)
- `src/teamsleech/services/scanner.py` (repair helper)
- `src/teamsleech/services/discovery.py` (normalized search)
- `.github/workflows/bot-runner.yml` (repair option)

**Estimated scope:** Medium (4–5 files)

## Checkpoint: Complete
- [ ] 9/9 subjects grabbing in live tally
- [ ] Ready for review
