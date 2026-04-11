# Phase 8 — Personal Control Dashboard

> **Status:** Not started  
> **Repo:** `<your-username>/<your-repo>` (private, GitHub Pro)  
> **Goal:** A lean, biometric-unlocked personal dashboard to trigger and monitor GitHub Actions runs — hosted on GitHub Pages, zero backend, zero extra cost.

---

## What This Phase Produces

Two new files added to the repo. Nothing else is modified.

```
TeamsLeech-Bot/
├── src/                    ← UNTOUCHED
├── tests/                  ← UNTOUCHED
├── .github/workflows/      ← UNTOUCHED
├── subjects_config.json    ← UNTOUCHED
├── docs/
│   └── index.html          ← NEW: the dashboard (single file)
└── scripts/
    ├── generate_session.py ← UNTOUCHED
    └── setup_gist.py       ← NEW: one-time credential setup
```

---

## Security Architecture (Understand Before Building)

```
Private GitHub Repo → source code invisible to public
        +
Private GitHub Gist → stores AES-256-GCM encrypted credentials
        +
Master password → stored in your phone's password manager
        +
Biometric (Face ID / Fingerprint) → unlocks master password
        ↓
Dashboard decrypts credentials in browser memory only
GH_PAT and BOT_TOKEN never written to disk, never in localStorage
```

**What lives where:**

| Item | Where | Risk if exposed |
|---|---|---|
| `GIST_ID` | Baked into `index.html` source | Low — just an ID, useless without the password |
| `GIST_READ_TOKEN` | Baked into `index.html` source | Low — read-only, only decrypts an encrypted blob |
| Master password | Your phone's password manager | The only real secret — protect this |
| `GH_PAT` | Decrypted in memory, never stored | Never exposed |
| `BOT_TOKEN` | Decrypted in memory, never stored | Never exposed |

---

## Build Phases

| Phase | File | Time | Description |
|---|---|---|---|
| [Phase A](./PHASE_A_SETUP.md) | `scripts/setup_gist.py` | 30 min | One-time credential encryption + Gist creation |
| [Phase B](./PHASE_B_DASHBOARD.md) | `docs/index.html` | 2 hours | The dashboard itself |
| [Phase C](./PHASE_C_DEPLOY.md) | GitHub Settings | 10 min | Enable GitHub Pages |
| [Phase D](./PHASE_D_BIOMETRIC.md) | Your phone | 5 min | Biometric unlock setup |

**Work through them in order. Do not skip ahead.**

---

## Master Checklist (tick as you go)

```
Phase A — Setup Script
□ pip install cryptography requests --break-system-packages
□ python scripts/setup_gist.py runs without errors
□ GIST_ID printed to terminal — copied somewhere safe
□ Private Gist visible at gist.github.com (should be listed)

Phase B — Dashboard
□ docs/index.html created by AI IDE
□ GIST_ID pasted into index.html at the marked location
□ GIST_READ_TOKEN pasted into index.html at the marked location  
□ Wire check prompt run — no mismatches found
□ Tested locally by opening index.html in browser

Phase C — Deploy
□ GitHub Pages enabled: Settings → Pages → /docs branch main
□ Dashboard loads at <your-username>.github.io/<your-repo>
□ Unlock screen appears (not a blank page, not an error)
□ Correct master password unlocks the dashboard
□ Wrong password shows error and clears field

Phase D — Biometric
□ Opened dashboard URL in Safari/Chrome on phone
□ Entered master password once
□ Phone prompted to save password — accepted
□ Closed tab, reopened, biometric autofill works
□ Tested from a second location (different WiFi)

Integration Tests
□ "▶ Run Workflow" button triggers a real Actions run
□ Status dot changes from grey → yellow during run
□ Status dot changes to green after completion
□ Usage meter shows correct minutes used
□ "⏹ Cancel Run" appears during active run and works
□ Lock icon returns to unlock screen and clears memory

Done — Phase 8 complete
```

---

## Files in This Folder

```
phase8/
├── README.md              ← You are here — start here
├── PHASE_A_SETUP.md       ← Setup script instructions + IDE prompt
├── PHASE_B_DASHBOARD.md   ← Dashboard build instructions + IDE prompt
├── PHASE_C_DEPLOY.md      ← GitHub Pages deployment steps
└── PHASE_D_BIOMETRIC.md   ← Mobile biometric setup steps
```

---

## Rules for This Phase

1. **Do not modify anything in `src/`** — the bot works, leave it alone
2. **Do not modify `workflow.yml`** — the dashboard calls it, doesn't change it
3. **If something breaks in the bot during this phase**, it is not related to the dashboard
4. **Run Phase A locally** — it needs terminal access to create the Gist
5. **Commit `docs/index.html` and `scripts/setup_gist.py` together** in one commit
