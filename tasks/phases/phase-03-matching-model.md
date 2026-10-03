# Phase 3 — Doctor + subject matching model (UI spec)

## Problem (your words)
Picking one doctor drags the other doctor's same-subject teams into results.

## Current behavior
`keywords=[team.display_name]` match only; `doctor` field is a rename label, never a filter.

## New behavior (logic; small UI surface)
- `SubjectConfig` gains `doctor_keywords: list[str] = []`.
- Team matches iff: subject-keywords hit AND (`doctor_keywords` empty OR doctor-keywords hit).
- Either list may be empty; at least one non-empty enforced at creation (Phase 4).

## UI surface
- Subject picker buttons unchanged (`short` labels).
- Results section header gains doctor line when set:
  ```
  📚 **Data Security**
  👨‍🏫 Dr. Hany Gouda
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  1. 👥 **Team-A** ...
  ```
- Cross-doctor teams simply absent (no message — cleanest; wrong entries were the complaint).

## Examples
| subject kw | doctor kw | team "Data Security - Dr Hany" | team "Data Security - Dr Soha" |
|---|---|---|---|
| data security | hany | ✅ | ❌ |
| data security | (empty) | ✅ | ✅ |
| (empty) | soha | ❌ | ✅ |

## Edge cases
- Old secrets lack `doctor_keywords` → default `[]` = today's behavior, zero migration.
- Case-insensitive, same word-boundary rules as subject keywords.

## Acceptance
- [ ] Matrix above covered in `test_scanner.py`
- [ ] Existing `SUBJECTS_JSON` loads unchanged
