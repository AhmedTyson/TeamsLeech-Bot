# Phase 7 — Progress visibility (UI spec)

## Diagnosis to confirm first (your report: "didn't see it")
Suspects: `file_progress` fires only on multiples of 5% (silent for small/fast
files); producer→consumer queue means nothing renders until first bytes land;
edits to one message race completion edits. Repro on a 2-file upload, then fix.

## New UI — one live message, exact evolution
Start (upload confirm):
```
☁️ **Uploading 2 files...**
📊 Progress: 0 / 2 files
```
Live message `📊` edits in place:
```
📊 **Uploading 2/2…**
1. ⬇️ 45% · 3.1 MB/s — Week 01 - L4…
2. ⏳ waiting — Lec-1.pdf
```
→ per file: `⬇️…` (download) → `⬆️ sending…` (Telegram upload) → `✅ done in 12s`.
- Download vs upload phases ALWAYS labeled (today only upload % shows).
- Updates on: every 5% AND every phase transition AND file boundaries (no silent files).
- Failures: standalone reply (keep current) — never inside this message.
- Finish (edit same message):
```
✅ **Upload complete!**
   ✔ 2 succeeded · ✘ 0 failed · 41s
```

## Rules
- One progress message per upload batch; no spam.
- Bar uses text percent (no emoji-bar precision loss); name truncated to 30 chars.
- FloodWait-safe: reuse `safe_edit_text`; min 2s between edits (coalesce).

## Edge cases
- Single file: same layout, 1 row.
- All fail: `❌ **Upload failed.**` + count, details already in standalone replies.

## Acceptance
- [ ] Root cause note written before fix
- [ ] Unit: 2-file callback sequence asserted (download % → sending → done ×2)
- [ ] Live 2-file upload watched by human
