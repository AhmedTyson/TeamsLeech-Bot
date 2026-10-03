# Custom Microsoft App Registration (instead of Azure CLI client)

The bot defaults to the Azure CLI first-party client ID with the `common`
tenant. If downloads are blocked for that client (Conditional Access approved-app
policies, tenant restrictions), register your own app. The bot picks it up via
`TEAMS_CLIENT_ID` / `TEAMS_TENANT_ID` secrets — no code change needed.

## 1. Create the registration

1. Go to `portal.azure.com` → **Microsoft Entra ID** → **App registrations** → **New registration**.
2. Name: `TeamsLeech-Bot`.
3. Supported account types: **Accounts in this organizational directory only** (single tenant — your university).
4. No redirect URI needed (device-code flow). Register.
5. Copy **Application (client) ID** and **Directory (tenant) ID** from the Overview page.

## 2. Allow device-code login

**Authentication** → Advanced settings → **Allow public client flows** → **Yes** → Save.

## 3. API permissions (delegated)

**API permissions** → Add a permission → add these **Delegated** permissions:

Microsoft Graph:
- `User.Read`
- `Team.ReadBasic.All`
- `Group.Read.All`
- `Sites.Read.All`
- `offline_access`

SharePoint (Office 365 SharePoint Online):
- `AllSites.Read`

Then **Grant admin consent** (needs an admin — ask university IT; one-time).
Without admin consent the login step fails until granted.

## 4. Wire secrets

GitHub repo → Settings → Secrets → Actions — add/update:

| Secret | Value |
|---|---|
| `TEAMS_CLIENT_ID` | Application (client) ID from step 1 |
| `TEAMS_TENANT_ID` | Directory (tenant) ID from step 1 |

Leave them unset to keep the Azure CLI defaults.

## 5. Log in with the new app

Actions → **TeamsLeech Bot** → Run workflow → `mode: reauth`.
The bot sends a device code in Telegram — complete it in the browser
(signed in as the downloading account). The new session is saved to
`TEAMS_REFRESH_TOKEN` automatically.

Reverting is safe: delete the two secrets and re-run `reauth` to go back
to the Azure CLI client.
