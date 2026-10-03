# Phase 11 — Subject keyword audit + auto-repair (plan)

## Problem (your words)
Searching still fails; configs miss; you can't see `SUBJECTS_JSON` (secret,
unreadable even to repo admins), so blind edits don't converge.

## Idea
Let the bot show and fix its own config: verify mode already reads the secret
at runtime. Extend it to (a) print every subject's exact keywords, (b) flag
bad ones, (c) propose additions, and — in a separate explicit mode — apply
safe additions and re-save the secret itself.

## Part A — Audit report (extends `mode=verify`, read-only)
Per subject, after the match lines, print:
```
📚 **<Name>** + 👨‍🏫 <doctor>: 1 team(s)
   🔎 subject keys: `a, b` | 🩺 doctor keys: `c`
   ✅ self-match OK — or — ❌ misses its own team `<Team>`!
   ⚠️ config: <validator flags, if any>
   💡 suggestions: <closest teams, if zero-match>
```
Rules: never print tokens/secrets, only names and keywords (goes to your
private chat — safe).

## Part B — Repair rules (new `mode=repair`, writes secret)
For each subject, automatically ADD (never delete) what's missing:
1. If subject matches 0 teams → add the suggested team display name (top
   `suggest_teams` hit) to subject keywords.
2. If subject matches its team already → ensure the team display name is IN
   subject keywords (self-match guarantee); add if absent.
3. Doctor keywords: NEVER auto-added (bleed risk) — reported only.
4. Re-validate everything with `validate_keyword_lists`; skip + report any
   subject still failing.
5. Save once via existing secret rotation; report before/after counts and run
   a fresh in-memory verify so the same message proves 9/9 (or lists leftovers).

## Safeguards
- Repair only ADDS keywords; user entries untouched, order kept.
- One secret write per run (not per subject).
- `verify` stays read-only; `repair` is the only writer. Run verify first,
  read the diff, then run repair.
- Rollback = `📚 Subjects` → edit (keywords visible in detail view).

## Search fix (same phase, add-flow search)
`discovery.search_teams` matches raw substring only. Extend to normalized
(squashed, punctuation-insensitive) substring as well, so `Data Security`
finds `BIS-DataSecurity-…`:
- keep 3-char minimum; return matches with `match_kind: exact|normalized`
- unit tests for both kinds.

## Acceptance
- [ ] Verify message shows every subject's keyword lists + flags + suggestions
- [ ] Repair run converts zero-match subjects to matched (unit + live)
- [ ] No user keyword ever deleted (unit: diff of lists)
- [ ] Search finds spaceless team names (unit)
- [ ] Full suite green
