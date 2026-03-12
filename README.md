# Flask App with Azure AD SSO

A Flask web application demonstrating Azure Active Directory (Azure AD) Single Sign-On (SSO) integration. Some pages are publicly accessible while others are protected and require users to authenticate with their organisation's Microsoft account.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [How Authentication Works](#how-authentication-works)
- [Pages](#pages)
- [Prerequisites](#prerequisites)
- [Azure AD App Registration](#azure-ad-app-registration)
- [Local Setup](#local-setup)
- [Running the App](#running-the-app)
- [Adding New Pages](#adding-new-pages)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

---

## Overview

This app uses the **Microsoft Authentication Library (MSAL)** for Python to implement the OAuth 2.0 Authorization Code flow with Azure AD. It is built on top of Flask and uses server-side sessions to store the authenticated user's identity.

Key features:
- Azure AD SSO — any member of your organisation can sign in via a **Sign in** button
- Mixed access — some pages are public, others require login
- Post-login redirect — users are sent back to the page they tried to visit before being asked to sign in
- Server-side sessions via `flask-session` (filesystem) — avoids browser cookie size limits caused by the MSAL token cache
- Token caching — MSAL token cache is stored server-side and used to silently refresh tokens without re-prompting the user
- CSRF protection on the OAuth callback via a `state` parameter

---

## Project Structure

```
flask_sso_app/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── .env.example            # Template for environment variables
├── .env                    # Your local environment variables (not committed)
├── .flask_session/         # Server-side session files (auto-created, not committed)
└── templates/
    ├── base.html           # Shared layout: nav bar, Sign in / Sign out button
    ├── home.html           # Public page — home
    ├── about.html          # Public page — about
    ├── dashboard.html      # Protected page — dashboard
    └── profile.html        # Protected page — user profile
```

---

## How Authentication Works

The app implements the **OAuth 2.0 Authorization Code Flow**:

```
User visits /dashboard (protected)
        │
        ▼
@login_required checks session
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
Microsoft redirects to /auth/callback with an authorization code
        │
        ▼
Flask exchanges code for tokens via MSAL
        │
        ▼
User claims (name, email, tenant) stored in Flask session
        │
        ▼
User redirected back to /dashboard
```

**Sign-out flow:**
1. Flask clears the local session
2. User is redirected to Microsoft's logout endpoint, which clears the Microsoft SSO session
3. User is returned to the home page

---

## Pages

| Route        | Access     | Description                                      |
|--------------|------------|--------------------------------------------------|
| `/`          | 🔓 Public  | Home page — visible to everyone                  |
| `/about`     | 🔓 Public  | About page — visible to everyone                 |
| `/dashboard` | 🔒 Protected | Dashboard — requires Azure AD sign-in          |
| `/profile`   | 🔒 Protected | User profile — requires Azure AD sign-in       |
| `/login`     | System     | Initiates the Azure AD OAuth flow                |
| `/auth/callback` | System | OAuth redirect URI — handles token exchange  |
| `/logout`    | System     | Clears session and redirects to Microsoft logout |

---

## Prerequisites

- Python 3.9 or higher
- An **Azure subscription** and access to **Azure Active Directory**
- Permission to register applications in your Azure AD tenant (or ask your Azure AD admin)

---

## Azure AD App Registration

You need to register this application in Azure AD before it can authenticate users. Follow these steps:

### Step 1 — Go to App Registrations

1. Sign in to the [Azure Portal](https://portal.azure.com)
2. Search for **Azure Active Directory** and open it
3. In the left menu, click **App registrations**
4. Click **+ New registration**

### Step 2 — Register the App

Fill in the form:

| Field | Value |
|-------|-------|
| Name | `My Flask SSO App` (or any name you prefer) |
| Supported account types | **Accounts in this organizational directory only** (single tenant) |
| Redirect URI | Platform: **Web**, URI: `http://localhost:5000/auth/callback` |

Click **Register**.

### Step 3 — Note Down the IDs

On the app overview page, copy:
- **Application (client) ID** → this is your `AZURE_CLIENT_ID`
- **Directory (tenant) ID** → this is your `AZURE_TENANT_ID`

### Step 4 — Create a Client Secret

1. In the left menu, click **Certificates & secrets**
2. Click **+ New client secret**
3. Add a description (e.g. `flask-local`) and choose an expiry
4. Click **Add**
5. **Copy the secret value immediately** — it won't be shown again
   This is your `AZURE_CLIENT_SECRET`

### Step 5 — Add Redirect URI for Production (optional)

If deploying to a server, add the production redirect URI:
1. Go to **Authentication** in the left menu
2. Under **Web → Redirect URIs**, add `https://yourdomain.com/auth/callback`

### Step 6 — API Permissions (optional)

The app requests `User.Read` by default (basic profile info). This is pre-consented. If you need additional Microsoft Graph permissions, add them under **API permissions**.

---

## Local Setup

### 1. Clone / Navigate to the folder

```bash
cd sample-adk-app/flask_sso_app
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
FLASK_SECRET_KEY=some-long-random-string-here
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=your-client-secret-value
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

> **FLASK_SECRET_KEY** — used to sign the session cookie. Use a long random string. You can generate one with:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

---

## Running the App

```bash
python app.py
```

The app starts on `http://localhost:5000`.

- Visit `http://localhost:5000` — public home page, no login needed
- Visit `http://localhost:5000/about` — public about page, no login needed
- Visit `http://localhost:5000/dashboard` — will redirect to SSO sign-in
- Visit `http://localhost:5000/profile` — will redirect to SSO sign-in

---

## Adding New Pages

### Add a public page (no login required)

1. Add a route in `app.py` — no decorator needed:

```python
@app.route("/docs")
def docs():
    return render_template("docs.html", user=session.get("user"))
```

2. Create `templates/docs.html` extending `base.html`:

```html
{% extends "base.html" %}
{% block title %}Docs — My App{% endblock %}
{% block content %}
<div class="card">
  <h1>Documentation</h1>
  <p>This is a public page.</p>
</div>
{% endblock %}
```

3. Add a link in `templates/base.html` nav.

---

### Add a protected page (login required)

1. Add a route in `app.py` with the `@login_required` decorator:

```python
@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", user=session["user"])
```

2. Create `templates/settings.html` extending `base.html`.

3. Add a link in `templates/base.html` nav with a 🔒 indicator.

That's all — `@login_required` handles everything else automatically.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FLASK_SECRET_KEY` | Yes | Secret key for signing Flask session cookies |
| `AZURE_CLIENT_ID` | Yes | Application (client) ID from Azure AD app registration |
| `AZURE_CLIENT_SECRET` | Yes | Client secret value from Azure AD app registration |
| `AZURE_TENANT_ID` | Yes | Directory (tenant) ID from Azure AD |

---

## Troubleshooting

### `AADSTS50011` — Redirect URI mismatch
The redirect URI in your `.env` / request does not match what is registered in Azure AD.
- Make sure `http://localhost:5000/auth/callback` is listed under **Authentication → Redirect URIs** in your Azure AD app registration.

### `State mismatch — possible CSRF`
The session expired or the browser lost the session between the login redirect and the callback.
- Ensure `FLASK_SECRET_KEY` is set and consistent.
- Do not open the callback URL directly in a browser.

### `KeyError: 'AZURE_CLIENT_ID'`
The `.env` file is missing or not loaded.
- Confirm `.env` exists in the `flask_sso_app/` directory and all three Azure variables are set.

### Sign-in works but user sees a blank name
The `name` claim may not be present for all account types. The templates fall back to `preferred_username` (the email address). This is normal for some guest or external accounts.

### Token expired / user gets logged out frequently
MSAL handles silent token refresh via the token cache stored in the server-side session. If the session itself expires, the user will need to sign in again. Session files are stored in `.flask_session/` — for production, consider switching `SESSION_TYPE` to `redis` for better scalability.

### Session cookie too large warning
If you see `UserWarning: The 'session' cookie is too large`, it means `flask-session` is not installed or not initialised correctly. Ensure `flask-session` is in `requirements.txt` and installed, and that `Session(app)` is called in `app.py`.
