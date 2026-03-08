# Phase A — One-Time Credential Setup

> **Time required:** 30 minutes  
> **Run this:** Once, locally on your machine  
> **Produces:** `scripts/setup_gist.py` + a private GitHub Gist containing your encrypted credentials

---

## What This Phase Does

Runs a Python script that:
1. Asks for your `GH_PAT`, `BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and a master password
2. Encrypts them using AES-256-GCM with a key derived from your master password
3. Creates a **private** GitHub Gist to store the encrypted blob
4. Gives you two values to paste into `docs/index.html`

After this phase, your real credentials never appear in any file ever again.

---

## Before You Start

**You need a GH_PAT with two scopes:**
- `repo` — to trigger and cancel workflow runs, read billing
- `gist` — to create the private Gist during setup

**To create one:**
1. GitHub → Settings → Developer Settings → Personal Access Tokens → Tokens (classic)
2. Generate new token (classic)
3. Scopes: check `repo` and `gist`
4. Copy the token immediately — you won't see it again

**You also need a separate read-only Gist token for the dashboard:**
1. Same place → Generate new token (classic)
2. Scopes: check `gist` only (nothing else)
3. Copy it — this one gets baked into the HTML source

> **Why two tokens?**  
> The first token (repo + gist) is powerful — used once during setup, then kept safe.  
> The second token (gist only) is read-only — safe to bake into the HTML since it can only read an encrypted blob.

---

## Step 1 — Install Dependencies

Open terminal in your project root and run:

```bash
pip install cryptography requests --break-system-packages
```

Expected output:
```
Successfully installed cryptography-41.x.x requests-2.x.x
```

If you see errors about permissions, add `--user` flag:
```bash
pip install cryptography requests --break-system-packages --user
```

---

## Step 2 — Create the Script Using Your AI IDE

Open your AI IDE (Cursor, Windsurf, etc.) in the project root.

**Create a new file:** `scripts/setup_gist.py`

**Paste this prompt exactly:**

---

```
Create a Python script at scripts/setup_gist.py for a project 
called TeamsLeech Bot.

The script must do the following in order:

STEP 1 - Collect inputs interactively:
  - Prompt for GH_PAT using getpass (hidden input)
  - Prompt for GIST_READ_TOKEN using getpass (hidden input)
    (explain in the prompt text: "This is your read-only gist token 
    for the dashboard HTML")
  - Prompt for BOT_TOKEN using getpass (hidden input)
  - Prompt for TELEGRAM_CHAT_ID using regular input
  - Prompt for master_password using getpass twice (confirm match)
  - If passwords don't match, print error and exit

STEP 2 - Encrypt the credentials:
  - Generate a random 32-byte salt using os.urandom(32)
  - Generate a random 12-byte IV using os.urandom(12)
  - Derive a 32-byte AES key using PBKDF2HMAC:
      algorithm: SHA256
      length: 32
      salt: the generated salt
      iterations: 310000
  - Encrypt the following JSON using AES-256-GCM:
      {"gh_pat": GH_PAT, "bot_token": BOT_TOKEN, "chat_id": TELEGRAM_CHAT_ID}
  - The encrypted output includes the GCM auth tag appended by the 
    cryptography library automatically

STEP 3 - Create a private GitHub Gist:
  - POST to https://api.github.com/gists
  - Auth header: Authorization: token {GH_PAT}
  - Body:
      {
        "description": "TeamsLeech Bot — encrypted dashboard credentials",
        "public": false,
        "files": {
          "teamsleech_credentials.json": {
            "content": JSON string of:
              {
                "salt": base64.b64encode(salt).decode(),
                "iv": base64.b64encode(iv).decode(),
                "ciphertext": base64.b64encode(ciphertext).decode()
              }
          }
        }
      }
  - If status code is not 201, print the error response and sys.exit(1)

STEP 4 - Print the results:
  Print a clearly formatted block:
  
  ============================================================
  SETUP COMPLETE — copy these two values into docs/index.html
  ============================================================
  
  GIST_ID = "{gist_id from response}"
  GIST_READ_TOKEN = "{the GIST_READ_TOKEN the user entered}"
  
  Paste both values at the top of docs/index.html
  where indicated by the comments.
  
  Keep your master password safe in your password manager.
  ============================================================

STEP 5 - Safety reminders:
  Print:
  - "Your GH_PAT and BOT_TOKEN are now encrypted. Do not store 
    them anywhere else."
  - "The Gist is private. Verify at: https://gist.github.com"

REQUIREMENTS:
  - Use only: cryptography, requests, base64, json, os, sys, getpass
  - Print a clear status message before each step so the user 
    knows what's happening
  - Wrap each step in try/except and print the error then sys.exit(1) on failure
  - Add a docstring at the top explaining what this script does
    and that it should be run once only
```

---

## Step 3 — Run the Script

```bash
python scripts/setup_gist.py
```

The script will walk you through inputs interactively. Every input is hidden (no echo on screen).

**Expected terminal flow:**
```
============================================================
  TeamsLeech Bot — Credential Setup
  Run this ONCE. Your credentials will be encrypted and
  stored in a private GitHub Gist.
============================================================

[1/5] Collecting credentials...
Enter your GH_PAT (repo + gist scope): 
Enter your GIST_READ_TOKEN (gist read-only scope):
Enter your BOT_TOKEN:
Enter your TELEGRAM_CHAT_ID: 
Enter master password: 
Confirm master password: 

[2/5] Encrypting credentials with AES-256-GCM...
✅ Encryption complete

[3/5] Creating private GitHub Gist...
✅ Gist created successfully

[4/5] Results:
============================================================
SETUP COMPLETE — copy these two values into docs/index.html
============================================================

GIST_ID = "a3f8c2..."
GIST_READ_TOKEN = "github_pat_xxxx..."

Paste both values at the top of docs/index.html
where indicated by the comments.
============================================================

[5/5] Reminders:
Your GH_PAT and BOT_TOKEN are now encrypted. Do not store them anywhere else.
The Gist is private. Verify at: https://gist.github.com
```

---

## Step 4 — Save the Output

Before doing anything else, copy the two printed values somewhere safe:

```
GIST_ID = "..."
GIST_READ_TOKEN = "..."
```

You will paste these into `docs/index.html` in Phase B. If you lose them, run the script again — it creates a new Gist each time (you can delete old ones).

---

## Step 5 — Verify the Gist Was Created

1. Open `https://gist.github.com` in your browser
2. You should see a Gist named **"TeamsLeech Bot — encrypted dashboard credentials"**
3. It should be marked **Secret** (private)
4. The file content should look like:
   ```json
   {
     "salt": "base64string...",
     "iv": "base64string...",
     "ciphertext": "base64string..."
   }
   ```
   (Not your actual credentials — just encrypted bytes)

---

## If Something Goes Wrong

**"401 Unauthorized" from GitHub API:**
Your GH_PAT is wrong or missing the `gist` scope. Create a new token with `repo` + `gist` scope.

**"Passwords do not match":**
Re-run the script. Type carefully — input is hidden.

**Import error for `cryptography`:**
```bash
pip install cryptography --break-system-packages --user
```

**Script created the Gist but you closed the terminal before copying the output:**
Go to `https://gist.github.com`, open the Gist, copy the Gist ID from the URL:
`https://gist.github.com/{username}/{THIS_IS_THE_GIST_ID}`

---

## Phase A Complete When

```
✅ script runs without errors
✅ GIST_ID saved
✅ GIST_READ_TOKEN saved
✅ Private Gist visible at gist.github.com
```

**Next:** [Phase B — Build the Dashboard](./PHASE_B_DASHBOARD.md)
