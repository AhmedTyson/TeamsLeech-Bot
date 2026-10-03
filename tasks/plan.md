# Implementation Plan: Fix 401 Unauthorized on SharePoint download (GitHub runner intermediary)

## Overview
`TransferService._download_recording` followed Graph `/content` 302s with auth headers attached and let SharePoint 401s escape as raw `HTTPStatusError` (no retry, no diagnosis). Fix: two-step download (Graph with auth, SharePoint bytes without auth), wrap all HTTP failures as `DownloadError`, distinguish Graph-side vs SharePoint-side 401s, prove with unit tests, then rerun the `TeamsLeech Bot` workflow and resolve any remaining tenant-side block (Conditional Access / Block-Download / view-only account).

## Architecture Decisions
- Two-step download instead of `follow_redirects=True`: Graph Bearer is for `graph.microsoft.com` audience only; SharePoint pre-authed `Location` URL carries its own token. No auth headers on step 2. (`src/teamsleech/services/transfer.py`)
- Catch `httpx.HTTPError` (covers `HTTPStatusError` + `RequestError`), re-raise as `DownloadError` so the existing `@_retry_download` (3 attempts) applies and `upload_ui` reports a meaningful message.
- Never log full download URL (contains `tempauth`); log host/path only.
- Tests mock `AsyncClient.get` (302) + `AsyncClient.stream` (bytes) separately and assert step 2 carries no `headers`.

## Task List

### Phase 1: Foundation (done)
- [x] Task 1: Diagnose 401 source
- [x] Task 2: Baseline test run

### Checkpoint: Foundation
- [x] Root cause identified (post-redirect SharePoint 401 + unhandled `HTTPStatusError`)

### Phase 2: Core fix (done)
- [x] Task 3: Rewrite `_download_recording` two-step
- [x] Task 4: Update + extend `test_transfer.py`

### Checkpoint: Core fix
- [x] 26/26 transfer tests, 127/127 unit, ruff clean

### Phase 3: Ship + live verify (todo)
- [ ] Task 5: Decide `uv.lock` hunk, commit, push
- [ ] Task 6: Rerun `TeamsLeech Bot` workflow, read new error/log line

### Checkpoint: Live verify
- [ ] Download succeeds, or error names Graph-side vs SharePoint-side

### Phase 4: Tenant-side resolution (conditional on Task 6)
- [ ] Task 7: Entra sign-in logs + site permission check
- [ ] Task 8: Conditional Access / Block-Download exemption or account scope fix

### Checkpoint: Complete
- [ ] File downloads via runner and reaches Telegram, or tenant block documented with owner action

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Runner IP blocked by tenant policy (not code) | High — code fix won't clear 401 | Task 6 log line distinguishes sides; Tasks 7–8 resolve tenant-side |
| Pre-authed URL expiry on large/slow downloads | Med | Immediate step-2 fetch; retry ×3; redirect logged |
| `uv.lock` version hunk pollutes diff | Low | Task 5 explicit keep/revert decision |

## Open Questions
- Does the failing file's site (`BIS-DataSecurity-Dr.HanyGouda-L4`) enforce Block-Download or view-only for the service account?
- Full SharePoint error body on runner (HTML snippet) — obtain from Task 6 logs?
