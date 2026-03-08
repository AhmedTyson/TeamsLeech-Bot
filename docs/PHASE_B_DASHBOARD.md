# Phase B — Build the Dashboard

> **Time required:** 2 hours  
> **Prerequisite:** Phase A complete — you have `GIST_ID` and `GIST_READ_TOKEN`  
> **Produces:** `docs/index.html` — the complete dashboard

---

## What This Phase Does

Creates a single HTML file that is your entire dashboard. No frameworks, no build step, no dependencies. Just one file committed to `/docs/` in your repo.

---

## Before You Start

Have these two values ready from Phase A:
```
GIST_ID = "..."
GIST_READ_TOKEN = "..."
```

---

## Step 1 — Create the Dashboard Using Your AI IDE

Open your AI IDE in the project root.

**Create a new file:** `docs/index.html`

**Paste this prompt exactly:**

---

```
Create a single-file dashboard at docs/index.html for a personal 
tool called TeamsLeech Bot. This is a private GitHub Pages site 
for one user only. No frameworks. No CDN imports. No external 
dependencies whatsoever.

PART 1 — CONSTANTS (at the very top of the <script> tag):

  // ── PASTE YOUR VALUES FROM setup_gist.py OUTPUT HERE ──
  const GIST_ID = "PASTE_GIST_ID_HERE";
  const GIST_READ_TOKEN = "PASTE_GIST_READ_TOKEN_HERE";
  // ────────────────────────────────────────────────────────
  const REPO = "AhmedTyson/TeamsLeech-Bot";
  const WORKFLOW_FILE = "workflow.yml";

  Leave GIST_ID and GIST_READ_TOKEN as placeholder strings.
  The user will replace them manually after the file is created.

PART 2 — UNLOCK SCREEN (shown on load, hidden after unlock):

  - Full-screen centered layout, dark background
  - Logo: 📡 emoji large, "TeamsLeech" heading below it
  - A single password input field:
      type="password"
      id="master-password" 
      autocomplete="current-password"
      placeholder="Master password"
  - An "Unlock" button below the field
  - Pressing Enter in the field submits (same as clicking Unlock)
  - An error message area below the button (hidden by default):
      id="unlock-error"
      text: "Incorrect password — try again"
      shown only on failed decryption
  - A subtle loading state on the button: "Unlocking..." while 
    decryption is in progress
  - The password field is cleared after a failed attempt

PART 3 — DECRYPTION FLOW (triggered on Unlock button click):

  Step A: Fetch the Gist
    GET https://api.github.com/gists/{GIST_ID}
    Header: Authorization: token {GIST_READ_TOKEN}
    Parse response → get files["teamsleech_credentials.json"].content
    Parse content as JSON → extract {salt, iv, ciphertext} (all base64)

  Step B: Derive the AES key using WebCrypto
    - Encode the password as UTF-8
    - Import as raw key material for PBKDF2
    - deriveKey with:
        algorithm: PBKDF2
        hash: SHA-256
        salt: decoded from base64
        iterations: 310000
        derivedKeyType: AES-GCM, length: 256

  Step C: Decrypt using AES-GCM
    - iv: decoded from base64
    - ciphertext: decoded from base64
    - On success: parse decrypted bytes as UTF-8 JSON
      → extract {gh_pat, bot_token, chat_id}
      → store in module-level JS variables (memory only)
      → call showDashboard()
    - On failure (wrong password): 
      → show unlock-error div
      → clear the password field
      → re-enable the Unlock button

PART 4 — DASHBOARD (hidden on load, shown after unlock):

  Layout: single column, max-width 480px, centered, 
  comfortable padding, mobile-first.

  HEADER:
    - Left: "📡 TeamsLeech" in purple
    - Right: a lock icon button (🔒)
    - Clicking lock: set gh_pat = null, bot_token = null, chat_id = null
      then hide dashboard, show unlock screen, clear password field

  CARD 1 — STATUS:
    Title: "Workflow Status"
    Content:
      - A colored dot + status text on one line:
          ⚫ grey dot = "Idle — no recent runs"
          🟡 yellow dot = "Running..."
          🟢 green dot = "Last run succeeded"  
          🔴 red dot = "Last run failed"
      - Below the dot: "Last run: {timestamp in local time}" 
        or "No runs found" if none
      - Auto-polls every 10 seconds using:
          GET https://api.github.com/repos/{REPO}/actions/runs?per_page=1
          Authorization: token {gh_pat}
        Parse runs[0].status and runs[0].conclusion
        status="in_progress" or "queued" → yellow
        conclusion="success" → green
        conclusion="failure" or "cancelled" → red
        No runs → grey
      - Store the current run_id from the most recent run for cancel

  CARD 2 — RUN CONTROL:
    Title: "Workflow Control"
    Content:
      State A (idle/completed): Show "▶ Run Workflow" button
        - On click: 
            POST https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches
            Body: {"ref": "main", "inputs": {"mode": "normal"}}
            Auth: token {gh_pat}
            On success: button shows "Starting..." for 3 seconds, 
            then status poll updates naturally
            On error: show a small red error text below the button
        - Button is full width, prominent, purple background

      State B (in_progress/queued): Show "⏹ Cancel Run" button instead
        - On click:
            POST https://api.github.com/repos/{REPO}/actions/runs/{run_id}/cancel
            Auth: token {gh_pat}
            On success: show "Cancelling..." then status updates naturally

  CARD 3 — USAGE METER:
    Title: "Actions Usage This Month"
    Content:
      - Polls once on load, then every 5 minutes:
          GET https://api.github.com/repos/{REPO}/actions/billing
          Auth: token {gh_pat}
          NOTE: If this endpoint returns 404, try:
          GET https://api.github.com/repos/{REPO}/actions/runs 
          and calculate manually from run durations as fallback
      - Shows: "{used} / 2000 min used"
      - Shows a progress bar below the text:
          Width proportional to used/2000
          Color:
            under 1500 → #22c55e (green)
            1500–1800  → #f59e0b (yellow/amber)
            above 1800 → #ef4444 (red)
      - If used > 1800: show a warning below the bar:
          "⚠️ Approaching monthly limit"

PART 5 — DESIGN SYSTEM:

  Colors:
    --bg: #0d0d0d
    --surface: #1a1a1a
    --border: #2a2a2a
    --accent: #8A2BE2
    --accent-hover: #7B27C1
    --text: #e5e5e5
    --text-muted: #888888
    --success: #22c55e
    --warning: #f59e0b
    --danger: #ef4444

  Typography:
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif
    Base size: 15px

  Cards:
    background: var(--surface)
    border: 1px solid var(--border)
    border-radius: 12px
    padding: 20px

  Buttons:
    border-radius: 8px
    padding: 12px 20px
    font-size: 15px
    font-weight: 600
    cursor: pointer
    transition: opacity 0.15s

  Run button:
    background: var(--accent)
    color: white
    width: 100%

  Cancel button:
    background: var(--danger)
    color: white
    width: 100%

  Status dots:
    display: inline-block
    width: 10px
    height: 10px
    border-radius: 50%
    margin-right: 8px

PART 6 — POLLING ARCHITECTURE:

  - On showDashboard(), start two intervals:
      pollStatus() every 10000ms (10 seconds)
      pollUsage() every 300000ms (5 minutes)
  - Call both immediately on dashboard show (don't wait for first interval)
  - On lock (hide dashboard), clear both intervals
  - All fetch calls include error handling:
      On network error: do not crash — just keep showing last known state
      On 401: show a small "Auth error" note in the affected card

PART 7 — STRUCTURE:

  <!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TeamsLeech</title>
    <style>
      /* all styles here */
    </style>
  </head>
  <body>
    <!-- unlock screen -->
    <!-- dashboard -->
    <script>
      /* all javascript here */
    </script>
  </body>
  </html>

  No external stylesheets. No external scripts. 
  Everything inline in this one file.

IMPORTANT — DO NOT ADD:
  - Any navigation beyond the three cards
  - Any Telegram chat interface
  - Any log viewer
  - Any settings page
  - Any animations beyond simple transitions
  Keep it lean. Three cards. One purpose.
```

---

## Step 2 — Paste Your Values

After the AI IDE creates `docs/index.html`, open it and find these two lines near the top of the `<script>` tag:

```javascript
const GIST_ID = "PASTE_GIST_ID_HERE";
const GIST_READ_TOKEN = "PASTE_GIST_READ_TOKEN_HERE";
```

Replace the placeholder strings with your actual values from Phase A:

```javascript
const GIST_ID = "a3f8c2d...";          // your actual Gist ID
const GIST_READ_TOKEN = "github_pat_..."; // your actual read-only token
```

Save the file.

---

## Step 3 — Run the Wire Check

Still in your AI IDE, paste this prompt in a **new chat or conversation**:

---

```
I have two new files in this project:
- scripts/setup_gist.py
- docs/index.html

Please review both files carefully and verify:

CHECK 1 — Encryption parameters match:
  setup_gist.py uses PBKDF2HMAC with SHA256, 310000 iterations, 
  32-byte key length, 32-byte salt, 12-byte IV.
  index.html uses WebCrypto PBKDF2 with SHA-256, 310000 iterations,
  AES-GCM 256-bit key.
  Confirm these are equivalent. If not, fix the mismatch.

CHECK 2 — JSON field names match:
  setup_gist.py writes a JSON object with fields: salt, iv, ciphertext.
  index.html reads fields named: salt, iv, ciphertext.
  Confirm they match exactly (case-sensitive). Fix if not.

CHECK 3 — Base64 encoding is consistent:
  setup_gist.py uses base64.b64encode (standard base64).
  index.html decodes using atob() or a Uint8Array approach.
  Confirm the encoding is standard base64 on both sides (not URL-safe).
  Fix if there is a mismatch.

CHECK 4 — WebCrypto API correctness:
  Confirm the algorithm name strings in index.html are exactly:
    "PBKDF2" for deriveKey
    "AES-GCM" for decrypt
  These are case-sensitive in WebCrypto. Fix if wrong.

CHECK 5 — GitHub API endpoints:
  Confirm these endpoints exist and the request format is correct:
    GET  /repos/{owner}/{repo}/actions/runs?per_page=1
    POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches
    POST /repos/{owner}/{repo}/actions/runs/{run_id}/cancel
    GET  /repos/{owner}/{repo}/actions/billing

CHECK 6 — Auth header format:
  Confirm both files use: Authorization: token {value}
  NOT: Authorization: Bearer {value}
  GitHub PAT auth uses "token" not "Bearer".

Report every issue found. Fix all issues directly in the files.
Do NOT modify anything in src/ or tests/ or workflow.yml.
```

---

## Step 4 — Local Test

Before committing, test the file locally:

1. Open `docs/index.html` directly in your browser (drag and drop, or `File → Open`)
2. The unlock screen should appear
3. Enter your master password
4. The dashboard should unlock and show three cards
5. The status card should show a real status (may show "No runs found" if no recent runs)

**Note:** The Gist fetch may fail locally due to CORS if the browser blocks it. If the unlock screen stalls, this is expected locally — it will work fine on GitHub Pages. Move to Phase C to test properly.

---

## Step 5 — Commit

```bash
git add docs/index.html scripts/setup_gist.py
git commit -m "Phase 8: personal dashboard (lean version)"
git push
```

---

## Phase B Complete When

```
✅ docs/index.html created
✅ GIST_ID and GIST_READ_TOKEN pasted in
✅ Wire check run — no mismatches
✅ File committed and pushed
```

**Next:** [Phase C — Enable GitHub Pages](./PHASE_C_DEPLOY.md)
