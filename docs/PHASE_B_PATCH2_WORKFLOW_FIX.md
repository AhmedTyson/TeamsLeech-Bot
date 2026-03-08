# Phase B — Patch 2: Workflow Control Fix

> **Problem:** The Run and Cancel buttons require multiple clicks
> or a full page refresh to reflect what GitHub Actions is
> actually doing. Three bugs cause this together.

---

## Root Cause Breakdown

**Bug 1 — Button freezes after one click**
The button disables itself and shows "Starting..." on click.
If the GitHub API call fails silently or returns an unexpected
status, the button never re-enables. You have to refresh.

**Bug 2 — Status dot doesn't update after clicking Run**
GitHub takes 10–20 seconds after a dispatch before the new
run appears in its API. The dashboard polls every 10 seconds.
If it just polled one second before you clicked Run, it won't
check again for 9 more seconds — and may miss the new run
entirely on that cycle. You see no change and assume it failed.

**Bug 3 — Cancel button doesn't appear without refresh**
The Cancel button only renders when `pollStatus()` detects
`status="in_progress"`. Because of Bug 2's timing gap, the
poll never sees the new run transition in time, so the Cancel
button never replaces the Run button automatically.

---

## IDE Prompt

Copy this exactly into your AI IDE as a new conversation:

---

```
Read docs/PRD.md, docs/phase8/README.md and docs/phase8/PHASE_B_DASHBOARD.md.

I have an existing docs/index.html that is working.
Fix the workflow control section only. Three bugs plus one
improvement. Do not touch the unlock screen, decryption,
usage meter, or any other part of the file.

─────────────────────────────────────────────────────────
BUG 1 — Button permanently disabled after one click
─────────────────────────────────────────────────────────
Location: the Run Workflow button click handler.

Current broken behavior:
  - Button disables and shows "Starting..."
  - If fetch() throws, or GitHub returns non-204, or any
    error occurs: button stays disabled forever
  - Only fix is a full page refresh

Fix required:
  Wrap the ENTIRE fetch call in try / catch / finally.

  try:
    - Set button disabled, text = "Starting..."
    - fetch POST to dispatch endpoint
    - If response.status === 204: success path (see Bug 2)
    - If response.status !== 204: throw new Error with status

  catch (err):
    - Show red error text below button: 
      "❌ Failed to start: " + err.message
    - Auto-hide the error after 5 seconds
    - Immediately re-enable the button, restore original text

  finally:
    - This block must NOT re-enable the button
      (success path handles its own state via fast poll)
    - Only the catch block re-enables immediately
    - The finally block is only for cleanup that always runs
      (e.g. clearing a timeout)

─────────────────────────────────────────────────────────
BUG 2 — Status does not update after clicking Run
─────────────────────────────────────────────────────────
Location: immediately after a successful 204 dispatch response.

Current broken behavior:
  - Dispatch succeeds (204)
  - Normal poll interval (10s) is already mid-cycle
  - May wait up to 10s before next check
  - GitHub itself takes 10–20s to show the new run
  - Combined: user sees nothing change for up to 30s
  - User thinks it failed, clicks Run again

Fix required:
  After receiving 204 from GitHub:

  STEP 1 — Optimistic UI immediately (before any poll):
    - Set status dot to yellow
    - Set status text to "Dispatching workflow..."
    - Show info text below button:
      "⏳ Waiting for GitHub to queue the run..."
    - Keep Run button disabled during this wait

  STEP 2 — Start a fast poll loop:
    - Clear the existing 10-second poll interval
    - Start a new interval polling every 2 seconds
    - Each fast poll calls pollStatus() normally
    - pollStatus() already reads run status from GitHub API

  STEP 3 — Detect when run appears:
    - In pollStatus(), after parsing the API response,
      check if runs[0].status === "queued" OR "in_progress"
    - AND check that runs[0].id is different from the run_id
      that was showing BEFORE the dispatch
      (store the pre-dispatch run_id in a variable called
      previousRunId before sending the dispatch request)
    - When both conditions are true: the new run is confirmed

  STEP 4 — On new run confirmed:
    - Stop the fast 2-second poll interval
    - Restart the normal 10-second poll interval
    - Clear the "Waiting for GitHub..." info text
    - Re-enable the Run button area
      (it will now show Cancel because status is in_progress)
    - If no new run appears within 30 seconds of dispatch:
      stop fast poll, restart normal poll, re-enable button,
      show warning: "⚠️ Run may not have started — check
      GitHub Actions tab"

─────────────────────────────────────────────────────────
BUG 3 — Cancel button requires page refresh to appear
─────────────────────────────────────────────────────────
Location: pollStatus() and the run control render logic.

Current broken behavior:
  - Run dispatched successfully
  - Cancel button should replace Run button automatically
  - But it only appears after a manual page refresh

This bug is resolved by Bug 2's fix IF the fast poll is
implemented correctly — the 2-second poll will detect
the queued/in_progress state and render the Cancel button.

Additionally fix these two things:

FIX A — Store currentRunId correctly:
  - Declare a module-level variable: let currentRunId = null
  - In pollStatus(), after parsing runs[0], always set:
    currentRunId = runs[0].id
  - The Cancel button click handler must read currentRunId
    at the moment of the click, not at the moment of render
    (closures capturing a stale value cause cancel to hit
    the wrong run ID or null)

FIX B — Cancel button re-enables correctly:
  - When Cancel is clicked: disable button, show "Cancelling..."
  - Wrap cancel fetch in try/catch/finally
  - On success (202 response): 
    show "Cancelled" text, start fast poll to confirm
    the run transitions to "cancelled" status
  - On failure: re-enable Cancel button, show error text
  - On confirmed cancel (pollStatus sees conclusion="cancelled"):
    restore Run button, clear status message

─────────────────────────────────────────────────────────
IMPROVEMENT — Instant visual feedback on every action
─────────────────────────────────────────────────────────
These small changes make the UI feel instant even when
the API is slow:

1. Run button clicked:
   - Immediately (synchronously, before any fetch):
     set dot to yellow, set text "Dispatching..."
   - If fetch ultimately fails: revert dot and text to
     whatever the last known real status was

2. Cancel button clicked:
   - Immediately: set dot to grey, set text "Cancelling..."
   - If fetch fails: revert to yellow / "Running..."

3. pollStatus() on network error:
   - Do not crash or clear the status display
   - Add a small grey indicator: "⚠️ Connection issue —
     retrying..." that disappears on next successful poll
   - Keep showing the last known status values

─────────────────────────────────────────────────────────
POLLING ARCHITECTURE SUMMARY after all fixes:
─────────────────────────────────────────────────────────

  Normal state (idle/completed):
    → 10-second poll interval running
    → Run button enabled

  After Run clicked (dispatched):
    → 2-second fast poll, max 30 seconds
    → Run button disabled, "Dispatching..." state
    → Switches back to 10-second poll when run detected

  While run in_progress:
    → 10-second poll interval running
    → Cancel button shown instead of Run button
    → currentRunId updated on every poll

  After Cancel clicked:
    → 2-second fast poll until conclusion=cancelled
    → Cancel button disabled, "Cancelling..." state
    → Switches back to 10-second poll, Run button restored

  On any network error:
    → Keep last known state visible
    → Keep polling, do not stop intervals on error

─────────────────────────────────────────────────────────
REQUIREMENTS:
─────────────────────────────────────────────────────────
- All changes inside docs/index.html only
- Do not change the unlock screen, AES decryption,
  Gist fetch, or usage meter
- Do not add any external libraries
- All fetch calls must have explicit timeout handling:
  use AbortController with a 15-second timeout on every
  GitHub API call so a hung request never freezes the UI
- Use async/await throughout, no raw .then() chains

Do not modify scripts/setup_gist.py.
Do not modify anything in src/, tests/, or .github/.
Do not touch workflow.yml or subjects_config.json.
```

---

## Test Checklist

Run these after the IDE applies the patch:

```
Run button behavior:
□ Click Run once → dot turns yellow instantly (before API responds)
□ Button shows "Starting..." and stays that way
□ "Waiting for GitHub to queue..." text appears below
□ Within 20 seconds: Cancel button appears automatically
  WITHOUT refreshing the page
□ "Waiting..." text disappears once run is detected
□ If GitHub API is down: error text appears after 15s,
  button re-enables, can click again immediately

Cancel button behavior:
□ While run is active: Cancel button is visible
□ Click Cancel once → dot turns grey instantly
□ Button shows "Cancelling..."
□ Within 10 seconds: status updates to cancelled/grey
  WITHOUT refreshing the page
□ Run button reappears after cancel confirmed
□ If cancel API call fails: Cancel button re-enables,
  error shown

Status polling:
□ Open dashboard while a run is already in_progress →
  Cancel button appears within 10 seconds, no click needed
□ Run completes while dashboard is open → dot turns green
  automatically, Run button reappears
□ Turn off WiFi for 20 seconds → "Connection issue" shown
  but last status is still visible
□ Turn WiFi back on → normal polling resumes, status updates

Edge cases:
□ Click Run rapidly twice → second click does nothing
  (button is disabled after first click)
□ Dispatch succeeds but run never appears in 30s →
  warning shown, button re-enables, no stuck state
```

## Gate Condition

Patch 2 is done when the Run button, Cancel button, and
status dot all update automatically within 20 seconds of
any workflow state change — with zero page refreshes
required under any normal operating condition.
