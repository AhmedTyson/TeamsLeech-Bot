# Todo: 401 Unauthorized download fix (ordered)

## Task 1: Diagnose 401 source

**Description:** Trace the failing SharePoint `download.aspx?UniqueId=...` URL to the exact code path and confirm why direct links work but the GitHub runner fails.

**Acceptance criteria:**
- [x] Failing URL identified as Graph `/content` 302 redirect target, not the Graph request itself
- [x] `httpx 0.28.1` cross-origin auth-stripping behavior verified in installed source
- [x] Unhandled `HTTPStatusError` path confirmed (`except RequestError` misses it; verified `issubclass` is `False`)

**Verification:**
- [x] `transfer.py:130-156` read; `_client.py:546-571` redirect logic read
- [x] `python -c` subclass check executed

**Dependencies:** None

**Files likely touched:**
- `src/teamsleech/services/transfer.py` (read-only)
- `src/teamsleech/tg_bot/handlers/upload_ui.py` (read-only)

**Estimated scope:** Small (2 files, read-only)

## Task 2: Baseline test run

**Description:** Run the existing transfer tests with the system Python 3.12 toolchain (uv-managed 3.13 cannot build `tgcrypto` on this machine) to record pre-fix state.

**Acceptance criteria:**
- [x] Baseline recorded: 21/23 pass, 2 fail only on Windows `/tmp` path (pre-existing, unrelated)

**Verification:**
- [x] `pytest tests/unit/test_transfer.py -v` executed

**Dependencies:** Task 1

**Files likely touched:** none

**Estimated scope:** XS (test run only)

## Checkpoint: After Tasks 1-2
- [x] Root cause written down before any code change
- [x] Baseline test result recorded

## Task 3: Rewrite `_download_recording` two-step

**Description:** Request Graph `/content` with `follow_redirects=False`; on 302 fetch `Location` with no auth headers; wrap Graph denials and SharePoint 401s as `DownloadError` with side-identifying messages; handle inline-200 and missing-`Location` edges.

**Acceptance criteria:**
- [x] Step 1 sends Graph Bearer, does not auto-follow
- [x] Step 2 sends no `Authorization` / `Accept: application/json`
- [x] SharePoint 401 raises `DownloadError` mentioning Conditional Access / Block-Download / permissions (retryable ×3)
- [x] Full download URL never logged (host/path only)

**Verification:**
- [x] Read edited `transfer.py:126-200`
- [x] `ruff check src/teamsleech/services/transfer.py` clean

**Dependencies:** Tasks 1–2

**Files likely touched:**
- `src/teamsleech/services/transfer.py`

**Estimated scope:** Small (1 file)

## Task 4: Update + extend `test_transfer.py`

**Description:** Remock the two-step flow (`get` → 302, `stream` → bytes), fix Windows `/tmp` paths via `tmp_path`, and add regression tests: SharePoint 401 wrapped as `DownloadError`, Graph 401 hint, missing `Location`, no-auth-forwarded assertion.

**Acceptance criteria:**
- [x] 26/26 transfer tests pass (incl. 3 new + 1 regression test)
- [x] No test writes outside `tmp_path`

**Verification:**
- [x] `pytest tests/unit/test_transfer.py -v` → 26 passed
- [x] `pytest tests/unit -q` → 127 passed

**Dependencies:** Task 3

**Files likely touched:**
- `tests/unit/test_transfer.py`

**Estimated scope:** Small (1–2 files)

## Checkpoint: After Tasks 3-4
- [x] 26/26 transfer tests pass
- [x] 127/127 unit tests pass, ruff clean
- [ ] Human reviews diff before push

## Task 5: Decide `uv.lock` hunk, commit, push

**Description:** `git diff` shows an unrelated `uv.lock` hunk (`teamsleech 2.1.0` → `2.3.1`, stale-lock side effect of the earlier `uv run`). Keep it only if intended (lock was stale vs `pyproject.toml:7`); otherwise `git checkout -- uv.lock`. Then commit the two real files and push.

**Acceptance criteria:**
- [ ] Diff contains only intended files (`transfer.py`, `test_transfer.py`, `tasks/plan.md`, `tasks/todo.md`, plus `uv.lock` iff deliberately kept)
- [ ] Commit pushed to `AhmedTyson/TeamsLeech-Bot`

**Verification:**
- [ ] `git status --short` shows expected set
- [ ] `git diff --stat` reviewed
- [ ] Push succeeds

**Dependencies:** Task 4

**Files likely touched:**
- `uv.lock` (keep or revert)
- `tasks/plan.md`, `tasks/todo.md` (new)

**Estimated scope:** XS (version control only)

## Task 6: Rerun workflow, read new log line

**Description:** Trigger the `TeamsLeech Bot` workflow (`workflow_dispatch`, same subject/file as the failure) and check whether download succeeds or which new side-identifying error appears (`Graph denied content [...]` vs `SharePoint download failed [401] ...`).

**Acceptance criteria:**
- [ ] Workflow run completed for the failing file
- [ ] Outcome recorded: success, Graph-side error, or SharePoint-side error

**Verification:**
- [ ] Actions log line for `Downloading: <name>` + `Graph redirect ...` captured
- [ ] Telegram result (`Upload complete` vs `failed: ...`) captured

**Dependencies:** Task 5

**Files likely touched:** none (Actions UI only)

**Estimated scope:** XS (remote run + log read)

## Checkpoint: After Tasks 5-6
- [ ] Download works end-to-end, or failing side (Graph vs SharePoint) is named by the new message
- [ ] Review with human before tenant-side changes

## Task 7: Entra sign-in logs + site permission check (conditional: SharePoint-side 401 persists)

**Description:** Confirm the service identity used by `TEAMS_REFRESH_TOKEN` has download (not view-only) rights on `BIS-DataSecurity-Dr.HanyGouda-L4` and find the 401 reason in Entra/SharePoint audit logs.

**Acceptance criteria:**
- [ ] Effective permission of the service account on the site library recorded
- [ ] Deny reason from logs recorded (policy vs permission vs expiry)

**Verification:**
- [ ] Site permissions screenshot / log excerpt saved
- [ ] Manual check: same account downloads the file in browser (proves code path vs rights)

**Dependencies:** Task 6

**Files likely touched:** none (tenant admin UI)

**Estimated scope:** Small (admin console only)

## Task 8: Exempt runner or fix account scope (conditional: Task 7 finds policy/permission block)

**Description:** Apply the minimal tenant fix: Conditional Access / compliant-network exemption for the runner path, Block-Download exclusion, or grant download rights / broaden token scope — then rerun Task 6.

**Acceptance criteria:**
- [ ] Minimal policy/account change applied and documented
- [ ] Workflow rerun downloads the file to Telegram

**Verification:**
- [ ] `Upload complete` in Telegram for the previously failing file
- [ ] Change recorded (what was exempted/granted, why minimal)

**Dependencies:** Task 7

**Files likely touched:** none (tenant admin UI; code unchanged unless scope string moves, then `src/teamsleech/services/auth.py`)

**Estimated scope:** Small (config only)
