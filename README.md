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

This app uses **Microsoft Authentication Library (MSAL)** for Python to implement OAuth 2.0 Authorization Code flow with Azure AD. Sessions are stored server-side using `flask-session` (filesystem) to avoid browser cookie size limits.

Key features:
- All pages require Azure AD sign-in — no public pages
- Role-based access via **Azure AD App Roles** — roles come directly in the ID token
- Admin tabs are hidden from non-admin users in the nav and blocked on the backend
- `@login_required` decorator for SSO-only pages
- `@role_required("admin")` decorator for admin-only pages
- Post-login redirect — users land on the page they originally requested
- CSRF protection on the OAuth callback via a `state` parameter
- Server-side filesystem sessions via `flask-session`

---

## Project Structure

```
flask_sso_app/
├── app.py                    # Main Flask application
├── requirements.txt          # Python dependencies
├── .env.example              # Template for environment variables
├── .env                      # Your local env variables (not committed)
├── .gitignore
├── .flask_session/           # Server-side session files (auto-created, not committed)
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

The app implements the **OAuth 2.0 Authorization Code Flow**:

```
User visits any page
        │
        ▼
@login_required / @role_required checks session
        │  no user in session
        ▼
Redirect to /login
        │
        ▼
Flask generates auth URL via MSAL → redirects to Microsoft login page
        │
        ▼
User signs in with their org Microsoft account
        │
        ▼
Microsoft redirects to /callback with an authorization code
        │
        ▼
Flask exchanges code for tokens via MSAL
        │
        ▼
User claims (name, email, roles, tenant) stored in server-side session
        │
        ▼
User redirected back to the original page
```

**Sign-out flow:**
1. Flask clears the local server-side session
2. User is redirected to Microsoft's logout endpoint
3. Microsoft clears the SSO session
4. User is returned to `/login`

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

### Step 7 — Verify the Redirect URI

1. Go back to **Azure Active Directory → App registrations → your app**
2. In the left menu, click **Authentication**
3. Under **Web → Redirect URIs**, confirm `http://localhost:3000/callback` is listed
4. If it is missing, click **+ Add URI**, enter `http://localhost:3000/callback`, and click **Save**

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
`flask-session` is not initialised correctly.
- Ensure `flask-session` is installed: `pip install flask-session`
- Confirm `Session(app)` is called in `app.py`
- Session files are stored in `.flask_session/` folder
