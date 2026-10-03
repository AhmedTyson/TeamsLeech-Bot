# Phase 5 — Numbered manage UI with edit (UI spec)

## Current UI (replace)
Dashboard text + one `❌ Delete <short>` button per subject (wall of buttons, delete-only).

## New UI
`/subjects` or `📚 Subjects` → numbered dashboard:
```
⚙️ **Subjects (3)** — tap a number:
1. **Data Security** — Dr. Hany Gouda
2. **Foreign Trade** — Dr. Azza Hegazy
3. **Math** — (no doctor)
[ 1 ]  [ 2 ]  [ 3 ]
[ ➕ Add New ]
```
- Tap number → detail + actions (message edit, same message):
  ```
  📚 **Data Security**
     🏷 Short: `DSEC`
     👨‍🏫 Doctor: `Dr. Hany Gouda`
     🔎 Subject keys: `data security`
     🩺 Doctor keys: `hany, gouda`
  [ ✏️ Edit ]  [ ❌ Delete ]  [ ⬅️ Back ]
  ```
- `❌ Delete` → confirm step:
  ```
  Delete **Data Security**? This removes it from tracking.
  [ Yes, delete ]  [ Keep ]
  ```
- `✏️ Edit` → field menu:
  ```
  What to edit for **Data Security**?
  [ 1 Name ]  [ 2 Short ]  [ 3 Doctor ]
  [ 4 Subject keys ]  [ 5 Doctor keys ]
  [ ⬅️ Back ]
  ```
  → prompt `Send new Short (current: \`DSEC\`), or \`keep\`.` → save → detail refresh + `✅ Short updated.`
- `➕ Add New` → existing (Phase 4) keyword flow.
- Pagination: >8 subjects → `[ ⬅️ Prev ] [ Next ➡️ ]` under numbers (reuse search-page pattern).

## Callbacks (new namespace, no clash)
`mng:list`, `mng:sel:<i>`, `mng:edit:<i>`, `mng:field:<i>:<f>`, `mng:del:<i>`, `mng:del_yes:<i>`, `mng:add`, `mng:page:<p>`.

## Edge cases
- Index out of range (edited elsewhere) → `Subject list changed — reopen 📚 Subjects.` alert.
- Secret-save failure → keep old values, show `❌ Failed to save… GH_PAT?` (existing wording).

## Acceptance
- [ ] Select → edit doctor only → persisted to secret (unit + live)
- [ ] Select → delete → confirm → gone (unit + live)
- [ ] Invalid index handled without crash
