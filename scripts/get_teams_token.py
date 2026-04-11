"""
Microsoft Teams Token Acquisition Script.

Uses the OAuth2 Device Code flow to obtain an initial refresh_token
for the Microsoft Graph API. The output should be stored in your
TEAMS_REFRESH_TOKEN GitHub Secret.

Usage
-----
    python scripts/get_teams_token.py
    # Follow the browser prompts to authenticate.
"""

import time
import requests

TENANT_ID = "common"
CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # Azure CLI (public)
SCOPE = "offline_access https://graph.microsoft.com/.default"


def get_ms_token() -> str | None:
    """Run the Device Code flow and return a refresh_token, or None on failure."""
    print("Requesting Device Code from Microsoft...")

    # 1. Request device code
    device_code_response = requests.post(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode",
        data={"client_id": CLIENT_ID, "scope": SCOPE},
    )

    if device_code_response.status_code != 200:
        print(f"Failed to get device code: {device_code_response.text}")
        return None

    device_code_data = device_code_response.json()

    print("\n" + "=" * 60)
    print("ACTION REQUIRED:")
    print(f"1. Open your browser and go to: {device_code_data['verification_uri']}")
    print(f"2. Enter this code: {device_code_data['user_code']}")
    print("=" * 60 + "\n")
    print("Waiting for you to log in... (Polling Microsoft every few seconds).")

    # 2. Poll for the token
    expires_in = device_code_data['expires_in']
    interval = device_code_data['interval']
    device_code = device_code_data['device_code']

    start_time = time.time()

    while time.time() - start_time < expires_in:
        time.sleep(interval)

        token_response = requests.post(
            f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": CLIENT_ID,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
        )

        token_result = token_response.json()

        if "error" in token_result:
            if token_result["error"] == "authorization_pending":
                continue  # User hasn't finished logging in yet
            else:
                print(f"\nError: {token_result.get('error_description', token_result['error'])}")
                return None

        print("\n✅ Successfully authenticated!")
        print("\nYour new refresh token is:\n")
        print(token_result["refresh_token"])
        print("\nCopy this token and use it to update your TEAMS_REFRESH_TOKEN GitHub Secret.")
        return token_result["refresh_token"]

    print("\nTimed out waiting for login.")
    return None


if __name__ == '__main__':
    get_ms_token()
