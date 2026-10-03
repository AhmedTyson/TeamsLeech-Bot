# Phase 10 — Full-text buttons research (last, adopt-or-document)

## Your note
Buttons are meant full-text; numbers hide meaning. Danger: long text + many
buttons = actions pushed out of view = worse UX.

## Facts to measure (live test, not memory)
- Telegram inline button text: no hard documented char cap in Bot API, but
  clients truncate roughly ~1 line; `callback_data` hard cap 64 bytes (use
  `sel:<i>` indices regardless of label).
- Hard caps: ≤100 buttons/message, ≤8 per row — full-text forces 1-per-row.
- 9 recordings (your real case): full-text = 9 rows + upload + filters + actions
  ≈ 13+ rows before actions visible. Numbers = ~5 rows total today.

## Spike (only if measures look viable)
Variant checklist with `✅ <truncated 40-char name>` 1-per-row on a 9-item
scan; human judges: can you reach Upload/Filters/Cancel without scrolling on
your phone? If no → stop, keep numbers.

## Decision rule
Adopt full-text ONLY if actions stay visible for typical (≤15-item) lists;
else document here: "numbers stay because …" with the measured row counts,
and close. No code without the measurement.

## Acceptance
- [ ] Measured row counts recorded in this file
- [ ] Adopt (with tests) or documented-keep; suite green either way
