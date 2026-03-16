# Flask App with Azure AD SSO + RBAC

A Flask web application with Azure Active Directory (Azure AD) Single Sign-On (SSO) and Role-Based Access Control (RBAC). All pages require sign-in. Admin-only pages are hidden from and inaccessible to non-admin users.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Access Control Summary](#access-control-summary)
- [How Authentication Works](#how-authentication-works)
- [How Role-Based Access Works](#how-role-based-access-works)
- [Prerequisites](#prerequisites)
- [Azure Portal Setup](#azure-portal-setup)
- [Local Setup](#local-setup)
- [Running the App](#running-the-app)
- [Adding New Pages](#adding-new-pages)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

---

## Overview

This app uses **Microsoft Authentication Library (MSAL)** for Python to implement the **OAuth 2.0 Authorization Code Flow with OpenID Connect (OIDC)**. User identity claims are stored in a Flask signed cookie session — no server-side session storage required, because only the small ID token claims are retained (no access token).

Key features:
- All pages require Azure AD sign-in — no public pages
- Role-based access via **Azure AD App Roles** — roles come directly in the ID token
- Admin tabs are hidden from non-admin users in the nav and blocked on the backend
- `@login_required` decorator for SSO-only pages
- `@role_required("admin")` decorator for admin-only pages
- Post-login redirect — users land on the page they originally requested
- CSRF protection on the OAuth callback via a `state` parameter
- Session stored in a **Flask signed cookie** (no flask-session needed — ID token claims are small)
- **ID token only** — no access token or Graph API calls. Only `email`, `openid`, `profile` scopes requested

---

## Project Structure

```
flask_sso_app/
├── app.py                    # Main Flask application
├── requirements.txt          # Python dependencies
├── .env.example              # Template for environment variables
├── .env                      # Your local env variables (not committed)
├── .gitignore
└── templates/
    ├── base.html             # Shared layout: nav bar, role badges, sign-out
    ├── home.html             # SSO page — any signed-in user
    ├── about.html            # SSO page — any signed-in user
    ├── dashboard.html        # Admin only
    ├── profile.html          # Admin only
    └── access_denied.html    # Shown on 403 — insufficient role
```

---

## Access Control Summary

| Route | Template | Access | Decorator |
|-------|----------|--------|-----------|
| `/` | home.html | Any signed-in user | `@login_required` |
| `/about` | about.html | Any signed-in user | `@login_required` |
| `/dashboard` | dashboard.html | Admin role only | `@role_required("admin")` |
| `/profile` | profile.html | Admin role only | `@role_required("admin")` |
| `/login` | — | System — initiates OAuth flow | — |
| `/callback` | — | System — handles token exchange | — |
| `/logout` | — | System — clears session + Microsoft logout | — |

**Nav bar visibility:**
- Signed-in user (no admin role): Home, About
- Signed-in admin: Home, About, Dashboard, Profile

---

## How Authentication Works

The app implements the **OAuth 2.0 Authorization Code Flow with OpenID Connect (OIDC)**.

This is the industry-standard, Microsoft-recommended flow for web applications that sign in users. It is more secure than the older Implicit Flow because the ID token is never exposed to the browser — it is exchanged server-to-server between Flask and Azure AD.

---

### High-level flow

```
User visits any page
        │
        ▼
@login_required / @role_required checks session
        │  no user in session
        ▼
Flask saves requested URL → redirects to /login
        │
        ▼
MSAL generates CSRF state token + Azure AD authorization URL
        │
        ▼
Browser redirected to Microsoft login page
        │
        ▼
User signs in with org Microsoft account (+ MFA if required by org policy)
        │
        ▼
Azure AD redirects browser to /callback with a short-lived authorization code
        │
        ▼
Flask validates CSRF state → exchanges code for ID token (server-to-server via MSAL)
        │
        ▼
ID token claims (name, email, roles) stored in signed session cookie
        │
        ▼
User redirected back to the original page they requested
```

---

### Step-by-step detail

#### Phase 1 — Login initiation

**Step 1** — User visits a protected page (e.g. `/dashboard`). No session cookie found.

**Step 2** — The `@login_required` or `@role_required` decorator saves the requested URL in the session (`session["next"]`) and redirects to `/login`.

**Step 3** — Flask's `/login` route:
- Generates a random UUID as a `state` token and stores it in the session (`session["auth_state"]`)
- Uses MSAL to build the Azure AD authorization URL with the following parameters:

```
https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize
  ?client_id=YOUR_CLIENT_ID
  &response_type=code
  &redirect_uri=http://localhost:3000/callback
  &scope=openid profile email
  &state=RANDOM_UUID
  &response_mode=query
```

**Step 4** — Flask returns a `302` redirect, sending the browser to the Microsoft login page.

---

#### Phase 2 — Microsoft login

**Step 5** — The browser loads the Microsoft login page hosted by Azure AD.

**Step 6** — The user enters their org credentials. Azure AD applies MFA if required by the organisation's Conditional Access policy.

**Step 7** — On successful authentication, Azure AD generates a short-lived **authorization code** (valid for ~10 minutes, single use) and redirects the browser back to the app:

```
http://localhost:3000/callback?code=AUTH_CODE&state=RANDOM_UUID
```

> The authorization code alone is useless — it cannot be used to get user data without also presenting the client secret, which only Flask holds.

---

#### Phase 3 — Token exchange (server-to-server)

**Step 8** — The browser follows the redirect and hits Flask's `/callback` route, delivering the authorization code.

**Step 9 — CSRF check** — Flask compares the `state` value in the request against the `state` stored in the session. If they do not match, the request is rejected with `400 State mismatch — possible CSRF`. This prevents an attacker from tricking a user into completing a login initiated by someone else.

**Step 10** — Flask (via MSAL) makes a **server-to-server POST** to Azure AD's token endpoint. The browser is not involved in this step:

```
POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token

grant_type=authorization_code
code=AUTH_CODE
client_id=YOUR_CLIENT_ID
client_secret=YOUR_CLIENT_SECRET   ← never leaves the server
redirect_uri=http://localhost:3000/callback
```

**Step 11** — Azure AD validates the code and client secret, then returns an **ID token** (a signed JWT):

```json
{
  "name": "John Doe",
  "preferred_username": "john@company.com",
  "email": "john@company.com",
  "roles": ["admin"],
  "tid": "your-tenant-id",
  "oid": "user-object-id",
  "iat": 1710000000,
  "exp": 1710003600
}
```

> The client secret is never sent to or visible in the browser at any point. This is the primary security advantage of the Authorization Code Flow over the deprecated Implicit Flow.

---

#### Phase 4 — Session and redirect

**Step 12** — Flask stores the ID token claims in the session cookie (`session["user"] = id_token_claims`). The token itself is discarded — only the claims are kept.

**Step 13** — Flask redirects the user to the original URL they requested (`session.pop("next")`), or to `/dashboard` as default.

**Step 14** — On the next request, `@role_required("admin")` reads `session["user"]["roles"]` and either renders the page or returns a `403 Access Denied`.

---

### Why Authorization Code Flow and not Implicit Flow?

| | Authorization Code Flow (this app) | Implicit Flow (deprecated) |
|---|---|---|
| ID token location | Returned to server only | Returned directly to browser |
| Client secret used | Yes — server-to-server | No |
| Token in browser history/logs | No | Yes (in URL fragment) |
| Microsoft recommendation | ✅ Recommended | ❌ Deprecated |

---

### Sign-out flow

1. User clicks **Sign out**
2. Flask calls `session.clear()` — removes the session cookie
3. Browser redirected to Microsoft's logout endpoint:
   ```
   https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout
     ?post_logout_redirect_uri=http://localhost:3000/login
   ```
4. Microsoft clears the SSO session across all Microsoft apps (Teams, Outlook, etc.)
5. User is returned to `/login`

> **Why redirect to `/login` and not `/`?**
> All pages including `/` require sign-in. Redirecting to `/` after logout would immediately trigger another SSO login, creating a loop. Redirecting to `/login` lets the user choose when to sign back in.

---

## How Role-Based Access Works

Azure AD App Roles are defined in your app registration. When a user signs in, Azure AD includes their assigned roles in the ID token as a `roles` claim:

```json
{
  "name": "John Doe",
  "preferred_username": "john@company.com",
  "roles": ["admin"]
}
```

Flask reads this claim and enforces access via the `@role_required` decorator. The nav bar also conditionally shows/hides tabs based on the user's roles.

**If a user has no role assigned**, they can access SSO pages (Home, About) but will see an Access Denied page if they try to reach admin routes directly.

---

## Token Strategy

The app requests **ID token only** — no access token or Microsoft Graph API calls are made.

| Token | Requested | Used |
|-------|-----------|------|
| ID token | ✅ Yes | ✅ Yes — user identity, name, email, roles |
| Access token | ❌ No | ❌ No — not needed |

**Scopes requested:**

| Scope | Added by | Purpose |
|-------|----------|---------|
| `openid` | MSAL automatically | Required for OIDC / ID token |
| `profile` | MSAL automatically | Name claim in ID token |
| `email` | Explicitly set | Email claim in ID token |

The `roles` claim is included in the ID token automatically by Azure AD when App Roles are assigned — no extra scope needed.

---

## Azure Portal Registration Request

When raising an app registration request in your organisation's Azure portal, use these answers:

| Question | Answer |
|----------|--------|
| Application name | `My Flask SSO App` |
| Application type | Web application |
| Single tenant or multi-tenant | Single tenant (org only) |
| Redirect / Callback URL | `http://localhost:3000/callback` (dev), `https://yourdomain.com/callback` (prod) |
| Logout URL | `http://localhost:3000/logout` (dev), `https://yourdomain.com/logout` (prod) |
| Will anyone sign into this application? | Yes — all org Associates (Assignment Required = No) |
| Token type needed | ID token only |
| Scopes required | `email`, `openid`, `profile` (no Graph API permissions needed) |
| Does the app store user data? | No — session only, cleared on logout |
| Access provided to specific AD groups? | Yes — `App-Admin` security group assigned the `admin` app role |
| MFA required? | As per org policy |

---

## Prerequisites

- Python 3.9 or higher
- An Azure subscription with access to Azure Active Directory
- Permission to register apps and manage enterprise applications in your Azure AD tenant
- **Azure AD Premium P1 or P2** if you want to assign roles to groups (not required for individual user assignment)

---

## Azure Portal Setup

Follow these steps in order. All steps are done in [portal.azure.com](https://portal.azure.com).

---

### Step 1 — Open Azure Active Directory

1. Sign in to [https://portal.azure.com](https://portal.azure.com)
2. In the top search bar, type **Azure Active Directory**
3. Click **Azure Active Directory** from the results
4. You are now in your organisation's Azure AD tenant

---

### Step 2 — Register a New Application

1. In the left menu, click **App registrations**
2. Click **+ New registration** at the top
3. Fill in the registration form:

   - **Name** — enter `My Flask SSO App` (or any name you prefer)
   - **Supported account types** — select **Accounts in this organizational directory only (Single tenant)**
     > This means only users in your org can sign in
   - **Redirect URI**
     - From the platform dropdown, select **Web**
     - In the URI field, enter: `http://localhost:3000/callback`

4. Click **Register** at the bottom
5. You will be taken to the app overview page

---

### Step 3 — Copy the App IDs

On the app overview page you just landed on:

1. Copy the **Application (client) ID** — paste it as `AZURE_CLIENT_ID` in your `.env`
2. Copy the **Directory (tenant) ID** — paste it as `AZURE_TENANT_ID` in your `.env`

> Keep this page open — you will come back to it for the next steps

---

### Step 4 — Create a Client Secret

1. In the left menu, click **Certificates & secrets**
2. Click the **Client secrets** tab
3. Click **+ New client secret**
4. Fill in the form:
   - **Description** — enter `flask-local`
   - **Expires** — choose `24 months` (or as per your org policy)
5. Click **Add**
6. A new row appears in the table — copy the **Value** column immediately
   > ⚠️ This value is only shown once. If you navigate away, you cannot retrieve it and will need to create a new secret.
7. Paste this value as `AZURE_CLIENT_SECRET` in your `.env`

---

### Step 5 — Define the Admin App Role

1. In the left menu, click **App roles**
2. Click **+ Create app role**
3. Fill in the form:

   | Field | Value |
   |-------|-------|
   | Display name | `Admin` |
   | Allowed member types | `Users/Groups` |
   | Value | `admin` |
   | Description | `Access to admin-only pages` |
   | Do you want to enable this app role? | ✅ Checked |

4. Click **Apply**
5. You will see the `admin` role listed in the App roles table

> The **Value** field (`admin`) must exactly match what is used in `@role_required("admin")` in `app.py`

---

### Step 6 — Assign Users to the Admin Role

This is done from a different section — **Enterprise applications**.

1. In the top search bar, type **Enterprise applications**
2. Click **Enterprise applications** from the results
3. Search for your app by name (`My Flask SSO App`) and click it
4. In the left menu, click **Users and groups**
5. Click **+ Add user/group** at the top

**Option A — Assign an individual user (works on free Azure AD tier):**

1. Click **None Selected** under Users
2. Search for the user by name or email
3. Click the user to select them (a checkmark appears)
4. Click **Select**
5. Click **None Selected** under Select a role
6. Click **Admin** from the list
7. Click **Select**
8. Click **Assign**

The user now appears in the list with role `Admin`.

**Option B — Assign a Security Group (requires Azure AD Premium P1/P2):**

First create the group:
1. Go back to **Azure Active Directory → Groups**
2. Click **+ New group**
3. Fill in:
   - **Group type** — `Security`
   - **Group name** — `App-Admin`
   - **Membership type** — `Assigned`
4. Click **Members → + Add members** — search and add users
5. Click **Create**

Then assign the group to the role:
1. Go to **Enterprise applications → your app → Users and groups**
2. Click **+ Add user/group**
3. Click **None Selected** under Users and groups — search for `App-Admin`
4. Select the group → click **Select**
5. Click **None Selected** under Select a role → choose `Admin` → click **Select**
6. Click **Assign**

> Anyone **not** in this assignment will sign in successfully but will only see Home and About. They will get an Access Denied page if they try to reach Dashboard or Profile directly.

---

### Step 7 — Verify the Redirect URI and Set Logout URL

1. Go back to **Azure Active Directory → App registrations → your app**
2. In the left menu, click **Authentication**
3. Under **Web → Redirect URIs**, confirm `http://localhost:3000/callback` is listed
4. If it is missing, click **+ Add URI**, enter `http://localhost:3000/callback`
5. Scroll down to **Front-channel logout URL**
6. Enter your HTTPS logout URL — Azure AD requires HTTPS for this field
   - **Local dev** — leave blank for now, your app logout still works independently
   - **Production** — enter `https://yourdomain.com/logout`
7. Click **Save**

> The front-channel logout URL tells Azure AD to notify your app when the user signs out from any Microsoft app (Teams, Outlook etc.), so your app can also clear its session. Azure AD requires this to be HTTPS — `http://localhost` is not accepted here.

---

### Step 8 — Verify Token Configuration (optional)

The `roles` claim is automatically included in the ID token when App Roles are assigned — no extra steps needed. To confirm:

1. In the left menu, click **Token configuration**
2. You do not need to add `roles` manually — it is natively included via App Roles
3. Optionally click **+ Add optional claim** → Token type: **ID** — you can add `email` here if you want the user's email in the token

---

### Step 9 — Add Production Redirect URI (when deploying)

When you deploy to a server, add the production callback URL:

1. **App registrations → your app → Authentication**
2. Under **Redirect URIs**, click **+ Add URI**
3. Enter `https://yourdomain.com/callback`
4. Click **Save**

> You can have multiple redirect URIs — keep `http://localhost:3000/callback` for local development

---

### Full Azure Portal Checklist

```
✅ App registered in Azure AD
✅ Client ID + Tenant ID copied to .env
✅ Client secret created and copied to .env
✅ App role "admin" defined with value exactly: admin
✅ Users or groups assigned the Admin role in Enterprise applications
✅ Redirect URI http://localhost:3000/callback confirmed in Authentication
✅ Front-channel logout URL set in Authentication (HTTPS only — leave blank for local dev, add on production)
```

---

## Local Setup

### 1. Navigate to the folder

```bash
cd sample-adk-app/flask_sso_app
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` and fill in your values:

```env
FLASK_SECRET_KEY=some-long-random-string-here
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=your-client-secret-value
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

> Generate a secure secret key:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

---

## Running the App

```bash
python app.py
```

App starts on `http://localhost:3000`. Any page will redirect to Azure AD login if not signed in.

---

## Adding New Pages

### SSO page (any signed-in user)

1. Add route in `app.py`:
```python
@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html", user=session["user"])
```

2. Create `templates/reports.html` extending `base.html`

3. Add link in `base.html` nav (visible to all signed-in users)

---

### Admin-only page

1. Add route in `app.py`:
```python
@app.route("/settings")
@role_required("admin")
def settings():
    return render_template("settings.html", user=session["user"])
```

2. Create `templates/settings.html` extending `base.html`

3. Add link in `base.html` nav inside the `{% if user and 'admin' in user.get('roles', []) %}` block

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FLASK_SECRET_KEY` | Yes | Secret key for signing session cookies |
| `AZURE_CLIENT_ID` | Yes | Application (client) ID from Azure AD app registration |
| `AZURE_CLIENT_SECRET` | Yes | Client secret from Azure AD app registration |
| `AZURE_TENANT_ID` | Yes | Directory (tenant) ID from Azure AD |

---

## Troubleshooting

### `AADSTS50011` — Redirect URI mismatch
The redirect URI doesn't match what's registered in Azure AD.
- Ensure `http://localhost:3000/callback` is listed under **App registrations → your app → Authentication → Redirect URIs**

### `State mismatch — possible CSRF`
Session expired between the login redirect and the callback.
- Ensure `FLASK_SECRET_KEY` is set in `.env`
- Do not open the callback URL directly in a browser

### `KeyError: 'AZURE_CLIENT_ID'`
The `.env` file is empty or missing.
- Confirm `.env` exists and all four variables are filled in

### Roles not appearing — user has no `roles` claim
The user has not been assigned an app role in Azure AD.
- Go to **Enterprise applications → your app → Users and groups**
- Assign the user (or their group) to the `Admin` role
- Sign out and sign back in — the token is only updated on new sign-in

### Groups not visible in Enterprise applications
Azure AD Premium P1/P2 license is required to assign groups to app roles.
- Use individual user assignment instead (free tier supported)

### Session cookie too large warning
This app stores only ID token claims in the session (no access token), so the cookie stays small (well under the 4KB browser limit). If you see this warning, check that you have not accidentally stored large objects in `session[]`.
