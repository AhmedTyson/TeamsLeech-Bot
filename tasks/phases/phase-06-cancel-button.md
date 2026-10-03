# Phase 6 — Cancel-only workflow button (UI spec)

## New UI
`/start` reply keyboard row 2 (replaces removed runner row):
```
[ 🛑 Cancel Workflow ]
```
- Idle tap → `💤 Runner idle — nothing to cancel.` (toast, no new message)
- Active tap → toast `Cancelling…`, then message:
  > `✅ Cancelled 1 run(s).`
- Errors (GitHub unreachable) → `❌ GitHub unreachable: <short>.` toast + keep keyboard.

## Behavior
- Backed by kept `get_active_runs` + `cancel_run` only.
- No trigger, no status list, no panel. `trigger_workflow` stays deleted.
- Callback namespace: `wflow:cancel` (fresh; no `act:*` revival).

## Edge cases
- Tap while run finishing naturally → `💤 Runner idle` (recheck after cancel returns empty).
- Double-tap race → second tap reports idle; harmless.

## Acceptance
- [ ] 2 active → cancels both, reports count (unit, mocked)
- [ ] 0 active → idle toast (unit)
- [ ] Live cancel of a real run verified
