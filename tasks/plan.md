# Implementation Plan: UI overhaul (10 phases)

## Overview
Rebuild the bot UX around three rules: scans always cover all joined teams over
the last 60 days unless the user scopes them (last-run filtering deleted, state
kept as knowledge only); subjects match doctor AND subject keywords (either
optional, at least one required); management uses numbered select-then-act
instead of button walls. Runner surface shrinks to a single cancel button.
Research spikes (rename buttons, full-text buttons) land last and only if viable.

## Architecture Decisions
- State (`last_run`/`last_lecture`) stays write-only knowledge; nothing filters on it.
- `SubjectConfig` gains `doctor_keywords`; matcher is AND across the two lists.
- Numbered selection reuses the scan-results pattern users already know.
- Cookie/token download chain untouched; progress work is display-only.
- Phases 9–10 are research-first; no edits without measured justification.

## Task List

### Phase 1: Delete runner
- [ ] Task: remove panel/trigger/status, keep cancel helpers for Phase 6

### Checkpoint: boots clean, no runner surface

### Phases 2–3: Scan + model
- [ ] Task: 60-day default scope, last-run filter deleted
- [ ] Task: doctor+subject AND matching

### Checkpoint: live scan verified

### Phases 4–5: Add + manage
- [ ] Task: add flow collects both keyword sets
- [ ] Task: numbered manage UI with edit + delete

### Checkpoint: full subject lifecycle live

### Phases 6–7: Cancel + progress
- [ ] Task: single cancel-workflow button
- [ ] Task: investigate + fix progress visibility

### Checkpoint: cancel + progress verified live

### Phase 8: Copy
- [ ] Task: truthful help, consistent tone

### Phases 9–10: Research spikes
- [ ] Task: rename-button friction decision
- [ ] Task: full-text button limits, adopt-or-document

### Checkpoint: Complete
- [ ] End-to-end live pass, ready for review

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| `SUBJECTS_JSON` schema drift (old secrets lack `doctor_keywords`) | Med | Pydantic defaults `[]`; migration check in Phase 3 tests |
| 60-day scan slower than incremental | Med | Keep per-team semaphore; measure live in Phase 2 |
| Cookie expiry confuses new UI testing | Low | Re-export flow already documented; error hint exists |
| Scope creep into download chain | High | Explicitly out of scope; display-only changes in Phase 7 |

## Open Questions
- Cancel button placement: reply keyboard row vs checklist action row? (Proposed: reply keyboard; confirm in Phase 6 review.)
- Raise/remove the 30-day range cap in Phase 2? (Proposed: align with 60-day default.)
- Edit flow: which fields editable? (Proposed: name, short, doctor, both keyword lists.)
