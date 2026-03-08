import time
import requests

TENANT_ID = "7b35586a-d18d-405c-8e29-5713862937a9"
CLIENT_ID = "5e3ce6c0-2b1f-4285-8d4b-75ee78787346"  # Official Teams Web Client
SCOPE = "offline_access https://graph.microsoft.com/.default"

def get_ms_token():
    print("Requesting Device Code from Microsoft...")
    
    # 1. Request device code
    res = requests.post(f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode", data={
        "client_id": CLIENT_ID,
        "scope": SCOPE
    })
    
    if res.status_code != 200:
        print(f"Failed to get device code: {res.text}")
        return None
        
    data = res.json()
    
    print("\n" + "="*60)
    print("ACTION REQUIRED:")
    print(f"1. Open your browser and go to: {data['verification_uri']}")
    print(f"2. Enter this code: {data['user_code']}")
    print("="*60 + "\n")
    print("Waiting for you to log in... (Polling Microsoft every few seconds).")
    
    # 2. Poll for the token
    expires_in = data['expires_in']
    interval = data['interval']
    device_code = data['device_code']
    
    start_time = time.time()
    
    while time.time() - start_time < expires_in:
        time.sleep(interval)
        
        token_res = requests.post(f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token", data={
            "client_id": CLIENT_ID,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code
        }, headers={"Origin": "https://teams.cloud.microsoft"})
        
        token_data = token_res.json()
        
        if "error" in token_data:
            if token_data["error"] == "authorization_pending":
                continue  # User hasn't finished logging in yet
            else:
                print(f"\nError: {token_data.get('error_description', token_data['error'])}")
                return None
        
        print("\n✅ Successfully authenticated!")
        print("\nYour new refresh token is:\n")
        print(token_data["refresh_token"])
        print("\nCopy this token and use it to update your TEAMS_REFRESH_TOKEN GitHub Secret.")
        return token_data["refresh_token"]
        
    print("\nTimed out waiting for login.")
    return None

if __name__ == '__main__':
    get_ms_token()
