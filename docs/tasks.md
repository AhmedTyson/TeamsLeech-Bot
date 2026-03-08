# TeamsLeech Bot — Milestones

## Phase 0 · Token Capture + Config ✅

**Done when:** `refresh_token` is captured via HAR and `subjects_config.json` lists all 6 subjects with keywords.
**Blockers:** None — first step.

---

## Phase 1 · Token Manager

**Done when:** `token_manager.py` exchanges a refresh_token for an access_token and auto-rotates the refresh_token back into GitHub Secrets.
**Blockers:** Phase 0 (valid refresh_token + GH_PAT secret).

---

## Phase 2 · Drive Fetcher

**Done when:** `fetcher.py` calls joinedTeams, filters by subject keywords, and returns a list of new `.mp4` files since last run.
**Blockers:** Phase 1 (working access_token).

---

## Phase 3 · Telegram Bot Interface

**Done when:** `bot.py` responds to `/check` with 6 subject buttons + Check All, handles text commands, and sends `/reauth` recovery instructions.
**Blockers:** Phase 2 (fetcher returns recording lists to display).

---

## Phase 4 · Upload Streamer

**Done when:** `uploader.py` streams selected recordings from Graph API to Telegram Saved Messages with 10%-increment progress messages.
**Blockers:** Phase 3 (user selection flow) + Phase 1 (valid access_token).

---

## Phase 5 · Orchestrator

**Done when:** `main.py` reads secrets from env vars and wires token_manager → fetcher → bot → uploader into a single entry point.
**Blockers:** Phases 1–4 (all modules functional).

---

## Phase 6 · GitHub Actions Workflow

**Done when:** `workflow.yml` runs `main.py` via `workflow_dispatch`, injects all secrets as env vars, and completes within free-tier limits.
**Blockers:** Phase 5 (working orchestrator).

---

## Phase 7 · End-to-End Test

**Done when:** A live `/check` → subject select → upload cycle delivers a recording to Telegram Saved Messages with zero manual intervention.
**Blockers:** Phase 6 (full pipeline deployed on Actions).
