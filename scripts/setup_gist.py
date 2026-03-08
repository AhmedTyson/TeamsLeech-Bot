"""
TeamsLeech Bot — One-Time Credential Setup Script

Run this script ONCE to:
  1. Collect your GitHub PAT, Gist read-only token, Bot token,
     Telegram chat ID, and a master password
  2. Encrypt the sensitive credentials using AES-256-GCM
  3. Upload the encrypted blob to a private GitHub Gist
  4. Print the GIST_ID and GIST_READ_TOKEN for use in docs/index.html

After running this script your real credentials are encrypted and
should not be stored anywhere else.
"""

import base64
import getpass
import json
import os
import sys

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    print("ERROR: 'cryptography' package is not installed.")
    print("Run:  pip install cryptography --break-system-packages")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package is not installed.")
    print("Run:  pip install requests --break-system-packages")
    sys.exit(1)


# ── STEP 1: Collect inputs interactively ────────────────────────────

def collect_inputs():
    """Prompt the user for all required credentials and the master password."""
    print()
    print("=" * 60)
    print("  TeamsLeech Bot — Credential Setup")
    print("  Run this ONCE. Your credentials will be encrypted and")
    print("  stored in a private GitHub Gist.")
    print("=" * 60)
    print()

    print("[1/5] Collecting credentials...")

    try:
        gh_pat = getpass.getpass("Enter your GH_PAT (repo + gist scope): ")
        if not gh_pat.strip():
            print("ERROR: GH_PAT cannot be empty.")
            sys.exit(1)

        gist_read_token = getpass.getpass(
            "Enter your GIST_READ_TOKEN (This is your read-only gist token for the dashboard HTML): "
        )
        if not gist_read_token.strip():
            print("ERROR: GIST_READ_TOKEN cannot be empty.")
            sys.exit(1)

        bot_token = getpass.getpass("Enter your BOT_TOKEN: ")
        if not bot_token.strip():
            print("ERROR: BOT_TOKEN cannot be empty.")
            sys.exit(1)

        chat_id = input("Enter your TELEGRAM_CHAT_ID: ")
        if not chat_id.strip():
            print("ERROR: TELEGRAM_CHAT_ID cannot be empty.")
            sys.exit(1)

        master_password = getpass.getpass("Enter master password: ")
        if not master_password:
            print("ERROR: Master password cannot be empty.")
            sys.exit(1)

        master_password_confirm = getpass.getpass("Confirm master password: ")
        if master_password != master_password_confirm:
            print("ERROR: Passwords do not match. Exiting.")
            sys.exit(1)

    except (KeyboardInterrupt, EOFError):
        print("\nAborted by user.")
        sys.exit(1)

    return gh_pat.strip(), gist_read_token.strip(), bot_token.strip(), chat_id.strip(), master_password


# ── STEP 2: Encrypt the credentials ────────────────────────────────

def encrypt_credentials(gh_pat, bot_token, chat_id, master_password):
    """Encrypt credentials JSON with AES-256-GCM using a PBKDF2-derived key."""
    print()
    print("[2/5] Encrypting credentials with AES-256-GCM...")

    try:
        # Generate random salt and IV
        salt = os.urandom(32)
        iv = os.urandom(12)

        # Derive a 32-byte AES key from the master password
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=310_000,
        )
        key = kdf.derive(master_password.encode("utf-8"))

        # Build the plaintext JSON
        plaintext = json.dumps({
            "gh_pat": gh_pat,
            "bot_token": bot_token,
            "chat_id": chat_id,
        }).encode("utf-8")

        # Encrypt with AES-256-GCM (tag is appended automatically)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, plaintext, None)

        print("✅ Encryption complete")
        return salt, iv, ciphertext

    except Exception as exc:
        print(f"ERROR during encryption: {exc}")
        sys.exit(1)


# ── STEP 3: Create a private GitHub Gist ────────────────────────────

def create_gist(gh_pat, salt, iv, ciphertext):
    """Upload the encrypted blob to a new private GitHub Gist."""
    print()
    print("[3/5] Creating private GitHub Gist...")

    try:
        gist_payload = {
            "description": "TeamsLeech Bot — encrypted dashboard credentials",
            "public": False,
            "files": {
                "teamsleech_credentials.json": {
                    "content": json.dumps({
                        "salt": base64.b64encode(salt).decode(),
                        "iv": base64.b64encode(iv).decode(),
                        "ciphertext": base64.b64encode(ciphertext).decode(),
                    }, indent=2)
                }
            }
        }

        response = requests.post(
            "https://api.github.com/gists",
            headers={
                "Authorization": f"token {gh_pat}",
                "Accept": "application/vnd.github.v3+json",
            },
            json=gist_payload,
            timeout=30,
        )

        if response.status_code != 201:
            print(f"ERROR: GitHub API returned {response.status_code}")
            print(response.text)
            sys.exit(1)

        gist_data = response.json()
        gist_id = gist_data["id"]

        print("✅ Gist created successfully")
        return gist_id

    except requests.RequestException as exc:
        print(f"ERROR during Gist creation: {exc}")
        sys.exit(1)
    except (KeyError, ValueError) as exc:
        print(f"ERROR parsing GitHub response: {exc}")
        sys.exit(1)


# ── STEP 4: Print results ──────────────────────────────────────────

def print_results(gist_id, gist_read_token):
    """Display the values the user needs to paste into index.html."""
    print()
    print("[4/5] Results:")
    print("=" * 60)
    print("SETUP COMPLETE — copy these two values into docs/index.html")
    print("=" * 60)
    print()
    print(f'GIST_ID = "{gist_id}"')
    print(f'GIST_READ_TOKEN = "{gist_read_token}"')
    print()
    print("Paste both values at the top of docs/index.html")
    print("where indicated by the comments.")
    print()
    print("Keep your master password safe in your password manager.")
    print("=" * 60)


# ── STEP 5: Safety reminders ───────────────────────────────────────

def print_reminders():
    """Print post-setup safety reminders."""
    print()
    print("[5/5] Reminders:")
    print("Your GH_PAT and BOT_TOKEN are now encrypted. Do not store them anywhere else.")
    print("The Gist is private. Verify at: https://gist.github.com")
    print()


# ── Main ────────────────────────────────────────────────────────────

def main():
    gh_pat, gist_read_token, bot_token, chat_id, master_password = collect_inputs()
    salt, iv, ciphertext = encrypt_credentials(gh_pat, bot_token, chat_id, master_password)
    gist_id = create_gist(gh_pat, salt, iv, ciphertext)
    print_results(gist_id, gist_read_token)
    print_reminders()


if __name__ == "__main__":
    main()
