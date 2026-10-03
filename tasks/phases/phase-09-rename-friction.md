# Phase 9 — Rename-button friction research (decision-first)

## Friction
Every checklist item renders `[✅ N] [✏️]` — rename (rare) doubles buttons vs select (common).

## Facts (verify, don't assume)
- Telegram has NO long-press/right-click callbacks → tap-toggles + hidden gestures impossible.
- Realistic options:
  - (a) Keep as-is.
  - (b) Select-then-act: footer gains `✏️ Rename` mode button; in rename mode number buttons become rename targets; `✔️ Done` exits mode.
  - (c) Rename moves into a per-file detail view (extra taps for the common case — likely worse).

## Mock for (b) if chosen
Default: `[✅ 3]` toggles. After `✏️ Rename`:
```
✏️ Rename mode — tap a file to rename it:
[ 1 ]  [ 2 ]  [ 3 ]
[ ✔️ Done ]
```
Tap number → existing suggestion flow (unchanged) → back to rename mode.

## Decision rule
Human approves (a)/(b) here first. Change code only for (b).

## Decision (recorded 2026-10-03)
**(a) Keep.** Telegram exposes no long-press/right-click callbacks, so (b)
adds a mode + Done button + new states to save one small `✏️` per item — net
negative for a rare action on a 2-person bot. Revisit only if checklist
regularly exceeds ~20 items.

## Acceptance
- [ ] Decision + Telegram-limits justification recorded in this file
- [ ] If (b): default view button count halved; toggle tests green + mode tests added
