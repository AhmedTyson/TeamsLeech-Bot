# Phase 4 — Add flow: subject + doctor (UI spec)

## Current flow
keyword → team list → pick team → Full Name → Short → Doctor|s`skip` → saved (`keywords=[team name]`).

## New flow (exact prompts)
1. User sends search keyword (as today) → numbered team results (unchanged).
2. Pick team → Step 1 Full Name (unchanged):
   > `📌 Adding: **<Team Name>**` … `📝 Step 1: Send the Full Name`
3. Step 2 Short Name (unchanged).
4. Step 3 — subject keywords (NEW):
   > `🔎 Step 3: Send SUBJECT keywords (e.g. \`Data Security\`), or \`skip\`.`
5. Step 4 — doctor keywords (NEW):
   > `👨‍🏫 Step 4: Send DOCTOR keywords (e.g. \`Hany\`), or \`skip\`.`
   > `_At least one of Steps 3–4 is required._`
6. Validation: skip+skip →
   > `❌ Give at least a subject or a doctor keyword. Send subject keywords, or \`skip\` to redo.`
   (returns to Step 3; `cancel` exits anywhere, unchanged)
7. Doctor display label: reuse existing ask (fold into Step 4 follow-up ONLY if doctor keywords given):
   > `Display name for the doctor? Send it, \`same\` to use your keywords, or \`skip\` for none.`
8. Save → success text gains the rule recap:
   > `✅ **<Name>** saved. Matches subject […] + doctor […].` (omit empty side)

## State machine
`pending_add_step`: `ask_name` → `ask_short` → `ask_subj_kw` → `ask_doc_kw` → (`ask_doc_label` if doc kw) → save. `pending_add_data` carries `subj_kw`, `doc_kw` lists (split on comma).

## Edge cases
- Keywords with commas → split into list; single word fine.
- Team search itself still uses the raw typed keyword (unchanged).

## Acceptance
- [ ] skip/skip rejected; other 3 combos save correctly (unit)
- [ ] `cancel` at each new step; live add verified
