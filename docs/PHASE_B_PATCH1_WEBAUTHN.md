# Phase B — Patch 1: WebAuthn Biometric Gate

> **Why this patch exists:** Chrome's built-in biometric autofill
> setting is inconsistent across Android versions and manufacturers.
> This patch adds a guaranteed OS-level fingerprint prompt directly
> inside the dashboard using the WebAuthn browser API — the same
> API used by banking apps. Works on all Android and iPhone
> regardless of Chrome or Safari version.

---

## What Changes

One addition to `docs/index.html` only. Nothing else is touched.

**Before this patch:**
```
Enter URL → Chrome autofills password silently → tap Unlock
```

**After this patch:**
```
Enter URL → Chrome autofills password silently →
tap "Confirm Identity" → fingerprint prompt (OS-level) →
authenticate → tap Unlock
```

---

## IDE Prompt

Copy this exactly into your AI IDE as a new conversation:

---

```
Read docs/PRD.md, docs/phase8/README.md and docs/phase8/PHASE_B_DASHBOARD.md.

I have an existing docs/index.html that is already working.
Do not rewrite it. Make one surgical addition only.

CONTEXT:
The dashboard currently has a password unlock screen. Chrome
autofills the password silently on mobile but does not prompt
for fingerprint because the Chrome biometric setting is
unavailable on this device. I need a guaranteed OS-level
fingerprint prompt using the WebAuthn browser API
(navigator.credentials.get) added directly to the unlock flow.

WHAT TO ADD:

1. WebAuthn registration (runs once, on first successful unlock):
   After the password decrypts successfully for the first time,
   before calling showDashboard(), call registerBiometric():

   async function registerBiometric() {
     Check if navigator.credentials exists — if not, skip silently.
     Check localStorage for key "webauthn_registered" — if "true",
     skip (already registered).

     Call navigator.credentials.create() with:
       publicKey: {
         challenge: crypto.getRandomValues(new Uint8Array(32)),
         rp: { name: "TeamsLeech" },
         user: {
           id: crypto.getRandomValues(new Uint8Array(16)),
           name: "owner",
           displayName: "Owner"
         },
         pubKeyCredParams: [
           { type: "public-key", alg: -7 },   // ES256
           { type: "public-key", alg: -257 }  // RS256
         ],
         authenticatorSelection: {
           authenticatorAttachment: "platform",
           userVerification: "required",
           residentKey: "discouraged"
         },
         // Force fingerprint over PIN/pattern — Android only honours
         // this when the device has biometric hardware enrolled
         timeout: 60000
       }

     On success: set localStorage "webauthn_registered" = "true"
                 set localStorage "webauthn_cred_id" = base64 of
                 credential.rawId (Uint8Array → base64 string)
     On failure or cancellation: skip silently, do not block unlock.
   }

2. WebAuthn verification (runs on every subsequent unlock attempt):
   Modify the unlock button click handler as follows:

   BEFORE attempting Gist fetch + decryption, check:
     - Does localStorage have "webauthn_registered" = "true"?
     - Does navigator.credentials exist?

   If YES to both: call verifyBiometric() first.
   If verifyBiometric() returns false: stop, show error
     "Biometric verification failed — try again"
   If verifyBiometric() returns true: proceed with Gist fetch
     and decryption as normal.

   If NO to either condition: proceed with Gist fetch and
   decryption directly (first-time flow, no biometric yet).

   async function verifyBiometric() {
     Retrieve stored cred ID from localStorage "webauthn_cred_id"
     Decode from base64 back to Uint8Array

     Call navigator.credentials.get() with:
       publicKey: {
         challenge: crypto.getRandomValues(new Uint8Array(32)),
         allowCredentials: [{
           id: credIdUint8Array,
           type: "public-key"
         }],
         userVerification: "required",
         timeout: 60000
       }

     On success: return true
     On failure or user cancellation: return false
   }

3. UI addition — biometric indicator:
   On the unlock screen, after the password field and before
   the Unlock button, add a small status line that is hidden
   by default:

   <p id="biometric-status"></p>

   When biometric registration completes after first unlock:
     Show: "🔐 Fingerprint registered — required on next unlock"
     Hide after 4 seconds

   When verifyBiometric() is called:
     Show: "👆 Touch the fingerprint sensor..."
   When it succeeds:
     Clear the text immediately
   When it fails:
     Show: "Biometric verification failed — try again"

4. Reset capability:
   Add a small text link below the Unlock button:
     "Reset biometric"
   Clicking it:
     Removes localStorage keys "webauthn_registered" and
     "webauthn_cred_id"
     Shows: "Biometric reset — will re-register on next unlock"
   This is the escape hatch if the registered credential becomes
   invalid (e.g. after a phone OS update or fingerprint change).

REQUIREMENTS:
  - All changes inside docs/index.html only
  - Do not change the password field, Gist fetch, AES decryption,
    or any dashboard panel logic
  - Do not add any external libraries or CDN imports
  - The biometric gate must be completely transparent when
    WebAuthn is not supported — degrade gracefully to password-only
  - Use async/await throughout, wrap in try/catch
  - Do not store any credential private key data — only the
    credential ID (rawId) which is not sensitive

AFTER making the changes, verify:
  - The unlock flow order is: fingerprint → password decrypt → dashboard
  - The first unlock (no biometric registered yet) still works
    without fingerprint
  - The reset link appears on the unlock screen
  - No existing functionality is broken

Do not modify scripts/setup_gist.py.
Do not modify anything in src/, tests/, or .github/.
Do not touch workflow.yml or subjects_config.json.
```

---

## Test Checklist

Run these after the IDE applies the patch:

```
First unlock (registration):
□ Open dashboard URL
□ Chrome autofills password
□ Tap Unlock — NO fingerprint prompt yet (first time)
□ Dashboard unlocks normally
□ "🔐 Biometric registered" message appears briefly
□ Dashboard shows three cards as before

Every unlock after registration:
□ Close tab, reopen URL
□ Chrome autofills password
□ Tap Unlock — OS fingerprint prompt appears immediately
□ Authenticate with fingerprint → dashboard unlocks
□ Wrong fingerprint → "Biometric verification failed" shown
□ Correct fingerprint → dashboard loads normally

Reset flow:
□ Tap "Reset biometric" link on unlock screen
□ "Biometric reset" message appears
□ Close tab, reopen, tap Unlock → no fingerprint prompt
  (back to first-time flow)
□ Unlock succeeds → biometric registers again

Graceful degradation:
□ If tested on a desktop browser without biometric hardware:
  unlock works normally with password only, no errors
```

## Gate Condition

Phase B Patch 1 is done when tapping Unlock on mobile triggers
an OS-level fingerprint prompt on every unlock after the first,
and the dashboard loads correctly after successful authentication.
