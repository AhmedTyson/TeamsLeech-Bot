# Phase 1 — Delete Background Runner feature (UI spec)

## Current UI (remove all of this)
- `/start` reply keyboard row 2: `[ ⚙️ Background Runner ]`
- `/runner` or tap → **GitHub Actions Control Panel** + inline:
  ```
  [ ▶️ Start Runner ]
  [ 🔄 Check Status ]
  [ 🛑 Cancel Active Runs ]
  ```
- Callbacks `act:run`, `act:status`, `act:cancel`; `test_run.py` dev script.

## New UI
- `/start` keyboard becomes single row:
  ```
  [ 🔍 Check Recordings ]  [ 📚 Subjects ]
  ```
- `/runner` typed → reply (no buttons):
  > `⚙️ Runner panel removed. Runs start on schedule / manual dispatch in GitHub. To stop one, use 🛑 Cancel Workflow (Phase 6).`
- No other trace: grep `act:`, `trigger_workflow`, `Background Runner` returns nothing.

## Flow
1. Delete `actions_ui.py`, trim `github_actions.py` to `get_active_runs` + `cancel_run` only (Phase 6 needs them).
2. Remove keyboard row, `/runner` handler body → notice text.
3. Delete `test_run.py`, `test_actions_ui.py`; shrink `test_github_actions.py` to kept helpers.
4. Full suite green.

## Edge cases
- User mid-tap on old panel message: callbacks unanswered → Telegram shows generic timeout; acceptable (panel messages age out).
- `github_actions` import in `main.py`? None currently — verify no dangling imports.

## Acceptance
- [ ] Boot log clean, `/start` shows 2 buttons
- [ ] `/runner` returns removal notice
- [ ] `pytest tests/unit -q` + `ruff` clean
