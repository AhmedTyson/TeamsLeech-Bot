"""
Phase 1 — Manual verification script for token_manager.

Prerequisites
-------------
1.  pip install requests pynacl python-dotenv
2.  Create a .env file in the project root with:
        TEAMS_REFRESH_TOKEN=<your token from HAR>
        GH_PAT=<your PAT with secrets:write>
        GITHUB_REPOSITORY=<your-username>/<your-repo>
3.  Run:  python tests/test_token_manager.py
"""

import os
import sys

# ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()  # load .env from project root

import requests as _requests
from token_manager import (
    exchange_refresh_token,
    rotate_github_secret,
    get_access_token,
    TokenExpiredError,
    TokenExchangeError,
    SecretRotationError,
)


def _pass(label: str) -> None:
    print(f"  ✅  {label}")


def _fail(label: str, err: Exception) -> None:
    print(f"  ❌  {label}: {err}")
    sys.exit(1)


def main() -> None:
    print()
    print("=" * 60)
    print("  Phase 1 — token_manager verification")
    print("=" * 60)

    rt  = os.environ.get("TEAMS_REFRESH_TOKEN", "")
    pat = os.environ.get("GH_PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    if not rt or not pat:
        print("\n  ❌  Missing TEAMS_REFRESH_TOKEN or GH_PAT in .env")
        sys.exit(1)

    # ── Test 1: Token exchange ───────────────────────────────────
    print("\n[1/4] Exchanging refresh_token for access_token...")
    try:
        access_token, new_rt = exchange_refresh_token(rt)
        assert access_token and len(access_token) > 100
        assert new_rt and len(new_rt) > 100
        _pass(f"Got access_token ({len(access_token)} chars)")
    except TokenExpiredError as e:
        _fail("Token expired — run /reauth flow", e)
    except TokenExchangeError as e:
        _fail("Token exchange failed", e)
    except Exception as e:
        _fail("Unexpected error", e)

    # ── Test 2: GitHub Secret rotation ───────────────────────────
    print("\n[2/4] Rotating refresh_token into GitHub Secrets...")
    try:
        rotate_github_secret(new_rt, repo, pat)
        _pass("Secret rotated successfully")
    except SecretRotationError as e:
        _fail("Secret rotation failed", e)
    except Exception as e:
        _fail("Unexpected error", e)

    # ── Test 3: Verify secret was written ────────────────────────
    print("\n[3/4] Verifying secret exists in GitHub...")
    try:
        resp = _requests.get(
            f"https://api.github.com/repos/{repo}/actions/secrets/TEAMS_REFRESH_TOKEN",
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        updated_at = resp.json().get("updated_at", "?")
        _pass(f"Secret exists — last updated: {updated_at}")
    except Exception as e:
        _fail("Secret verification failed", e)

    # ── Test 4: Graph API call with access_token ─────────────────
    print("\n[4/4] Calling Graph API /me to confirm access_token works...")
    try:
        me_resp = _requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        assert me_resp.status_code == 200, f"Expected 200, got {me_resp.status_code}"
        me = me_resp.json()
        _pass(f"Authenticated as: {me.get('displayName', '?')} ({me.get('mail', '?')})")
    except Exception as e:
        _fail("Graph API call failed", e)

    # ── Summary ──────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  All 4 checks passed ✅  — Phase 1 is DONE")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
