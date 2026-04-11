# Phase C — Deploy to GitHub Pages

> **Time required:** 10 minutes  
> **Prerequisite:** Phase B complete — `docs/index.html` pushed to `main`  
> **Produces:** Live dashboard at `<your-username>.github.io/<your-repo>`

---

## Step 1 — Enable GitHub Pages

1. Go to `https://github.com/<your-username>/<your-repo>`
2. Click **Settings** (top navigation, not the repo description)
3. In the left sidebar, scroll to **Pages**
4. Under **Source**, select:
   - Branch: `main`
   - Folder: `/docs`
5. Click **Save**

GitHub will show a banner:
> "Your site is being published at https://<your-username>.github.io/<your-repo>"

---

## Step 2 — Wait for Deploy (2-3 minutes)

GitHub Pages takes a moment to build. You can watch progress:

1. Go to your repo → **Actions** tab
2. Look for a workflow called **pages build and deployment**
3. Wait for it to show a green checkmark

---

## Step 3 — Open the Dashboard

Go to:
```
https://<your-username>.github.io/<your-repo>
```

You should see the unlock screen with the password field.

---

## Step 4 — Verify Everything Works

Run through this in order. Do not skip steps.

**Unlock test:**
```
□ Unlock screen appears (not a blank page)
□ Enter WRONG password → "Incorrect password" error appears
□ Wrong password field is cleared after error
□ Enter CORRECT master password → dashboard unlocks
```

**Status card test:**
```
□ Status card appears with a colored dot
□ If you have recent runs: dot shows correct color
□ If no recent runs: shows "Idle — no recent runs"
□ Timestamp shows or "No runs found" message shows
```

**Run button test:**
```
□ "▶ Run Workflow" button is visible
□ Click it → button shows "Starting..."
□ Go to GitHub Actions tab → a new run appears (may take 10-15 seconds)
□ Come back to dashboard → status dot turns yellow (may take up to 10s poll)
□ After run completes → dot turns green
```

**Cancel test (optional — only if you want to test it):**
```
□ Trigger a run with the Run button
□ While it's running: Cancel button appears instead of Run button
□ Click Cancel → run is cancelled in GitHub Actions
```

**Usage meter test:**
```
□ Usage meter shows a number like "203 / 2000 min used"
□ Progress bar is visible and colored correctly
```

**Lock test:**
```
□ Click the 🔒 icon top right
□ Dashboard hides, unlock screen reappears
□ Password field is empty
□ No credentials remain accessible
```

---

## If Something Goes Wrong

**Blank page at the URL:**
The deploy may not have finished. Wait 3 minutes and refresh.
If still blank, check GitHub Actions → pages build and deployment for errors.

**Unlock screen appears but decryption always fails:**
The GIST_ID or GIST_READ_TOKEN in `index.html` may be wrong.
Re-open `docs/index.html`, check the two constants at the top of the script.
Compare them exactly to the output from `setup_gist.py`.

**"Auth error" appears in the status card:**
The `gh_pat` stored in your Gist may have expired or have the wrong scope.
Re-run `python scripts/setup_gist.py` to create a fresh Gist with a new PAT.
Update `GIST_ID` in `index.html`, commit, push.

**Run button does nothing / shows error:**
Check that your `gh_pat` has `repo` scope, not just `gist`.
The workflow dispatch endpoint requires `repo` scope.

---

## Phase C Complete When

```
✅ Dashboard live at <your-username>.github.io/<your-repo>
✅ Unlock works correctly
✅ Run Workflow button triggers a real Actions run
✅ Status dot updates correctly
✅ Usage meter shows correct numbers
✅ Lock button clears everything and returns to unlock screen
```

**Next:** [Phase D — Biometric Setup](./PHASE_D_BIOMETRIC.md)

---
---

# Phase D — Biometric Unlock Setup

> **Time required:** 5 minutes  
> **Do this on:** Your phone  
> **Result:** One fingerprint/Face ID tap opens the fully unlocked dashboard

---

## How This Works

Your phone's password manager (iCloud Keychain on iPhone, Google Password Manager on Android) can save the master password for your dashboard URL. Once saved, biometrics (Face ID or fingerprint) autofills it whenever you visit the page. You never type it again.

This is standard browser behavior — nothing custom, nothing that can break.

---

## iPhone — Safari + iCloud Keychain

**Step 1: Open the dashboard in Safari**
```
https://<your-username>.github.io/<your-repo>
```
Safari specifically is required for iCloud Keychain autofill on the first save.

**Step 2: Enter your master password manually (once)**
- Tap the password field
- Type your master password
- Tap Unlock

**Step 3: Let Safari save the password**
- After the dashboard unlocks, Safari should prompt:
  > "Would you like to save this password?"
- Tap **Save Password**
- If the prompt doesn't appear: tap the share icon → **Passwords** → Save

**Step 4: Verify biometric autofill**
- Close the tab
- Reopen `https://<your-username>.github.io/<your-repo>`
- Tap the password field
- Your phone should show a Face ID / Touch ID prompt
- Authenticate → field autofills → tap Unlock

From now on: **URL → Face ID → Unlock. Done.**

**If autofill doesn't trigger:**
Settings → Safari → AutoFill → confirm "Passwords" is enabled.

---

## Android — Chrome + Google Password Manager

**Step 1: Open the dashboard in Chrome**
```
https://<your-username>.github.io/<your-repo>
```

**Step 2: Enter your master password manually (once)**
- Tap the password field
- Type your master password
- Tap Unlock

**Step 3: Let Chrome save the password**
- Chrome shows a prompt at the bottom:
  > "Save password for <your-username>.github.io?"
- Tap **Save**

**Step 4: Verify biometric autofill**
- Close the tab
- Reopen the URL
- Tap the password field
- Chrome shows fingerprint prompt
- Authenticate → field autofills → tap Unlock

**If autofill doesn't trigger:**
Settings → Google → Autofill → Passwords → confirm it's enabled.

---

## Add to Home Screen (Optional but Recommended)

Makes the dashboard feel like a native app. One tap from your home screen.

**iPhone:**
1. Open the dashboard URL in Safari
2. Tap the share icon (box with arrow)
3. Scroll down → **Add to Home Screen**
4. Name it "TeamsLeech"
5. Tap **Add**

**Android:**
1. Open the dashboard URL in Chrome
2. Tap the three-dot menu
3. Tap **Add to Home screen**
4. Name it "TeamsLeech"
5. Tap **Add**

Now your home screen has a TeamsLeech icon. Tap it → Face ID / fingerprint → dashboard open. Identical to opening an app.

---

## Accessing From a Different Device (Rare)

If you're on a device that doesn't have your password manager:

1. Open `https://<your-username>.github.io/<your-repo>`
2. Open your password manager app on your phone
3. Find the entry for `<your-username>.github.io`
4. Copy the master password
5. Paste it into the dashboard

This is the rare case. For your own phone it's always one biometric tap.

---

## Phase D Complete When

```
✅ Dashboard URL saved in phone's password manager
✅ Biometric autofill works: open URL → Face ID → unlock
✅ Home screen shortcut added (optional but recommended)
✅ Tested: close tab → reopen → biometric → dashboard loads
```

---
---

# Phase 8 — Done

All four phases complete. Your dashboard is live.

**What you have:**
- `scripts/setup_gist.py` — one-time setup script (commit it, it's safe — no secrets in it)
- `docs/index.html` — your dashboard (commit it, it's safe — secrets only in memory after unlock)
- A private Gist containing your encrypted credentials
- A biometric-unlocked dashboard at `<your-username>.github.io/<your-repo>`
- One-tap workflow trigger from anywhere in the world

**What remains completely unchanged:**
- All `src/` scripts
- All `tests/` files
- `workflow.yml`
- `subjects_config.json`
- The bot itself

**Update log:**
```
tasks.md → add Phase 8 ✅
docs/PRD.md → update Status to v1.2, add Phase 8 row to Build Phases table
```
