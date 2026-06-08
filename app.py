"""
Flask app with Azure AD SSO + Role-Based Access Control (RBAC).

Public pages    : /  (home), /about
Protected pages : /profile   — any logged-in user (admin, user, viewer)
                  /dashboard — admin only
"""
import os
import uuid
import json
import logging
import msal
from functools import wraps
from flask import (
    Flask, render_template, redirect, request,
    session, url_for, abort
)
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# ── Azure AD config ──────────────────────────────────────────────────────────
CLIENT_ID     = os.environ["AZURE_CLIENT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]
TENANT_ID     = os.environ["AZURE_TENANT_ID"]

AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_PATH = "/callback"
SCOPE         = ["email"]   # openid + profile added automatically by MSAL — ID token only, no Graph API


# ── Auth decorators ───────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            logger.info("[AUTH] No session found — redirecting to /login. Requested URL: %s", request.url)
            session["next"] = request.url
            return redirect(url_for("login"))
        logger.info("[AUTH] Session valid — user: %s", session["user"].get("preferred_username"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Decorator that requires the user to have one of the specified Azure AD App Roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("user"):
                logger.info("[ROLE] No session found — redirecting to /login. Requested URL: %s", request.url)
                session["next"] = request.url
                return redirect(url_for("login"))
            user_roles = session["user"].get("roles", [])
            logger.info("[ROLE] User: %s | Roles in token: %s | Required: %s",
                session["user"].get("preferred_username"), user_roles, list(roles))
            if not any(r in user_roles for r in roles):
                logger.warning("[ROLE] Access denied — user %s does not have required role %s",
                    session["user"].get("preferred_username"), list(roles))
                return render_template("access_denied.html", user=session["user"], required_roles=roles), 403
            logger.info("[ROLE] Access granted — user %s has required role", session["user"].get("preferred_username"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route("/login")
def login():
    logger.info("[LOGIN] Step 1 — /login hit, generating CSRF state token")
    state = str(uuid.uuid4())
    session["auth_state"] = state
    logger.info("[LOGIN] Step 2 — CSRF state saved in session: %s", state)

    logger.info("[LOGIN] Step 3 — Building MSAL ConfidentialClientApplication")
    logger.info("[LOGIN]          CLIENT_ID  : %s", CLIENT_ID)
    logger.info("[LOGIN]          AUTHORITY  : %s", AUTHORITY)
    logger.info("[LOGIN]          SCOPE      : %s", SCOPE)
    cca = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET,
    )

    logger.info("[LOGIN] Step 4 — Generating Azure AD authorization URL")
    auth_url = cca.get_authorization_request_url(
        SCOPE,
        state=state,
        redirect_uri=url_for("auth_callback", _external=True),
    )
    logger.info("[LOGIN] Step 5 — Redirect URI: %s", url_for("auth_callback", _external=True))
    logger.info("[LOGIN] Step 6 — Redirecting browser to Microsoft login page")
    logger.debug("[LOGIN] Full auth URL: %s", auth_url)
    return redirect(auth_url)


@app.route(REDIRECT_PATH)
def auth_callback():
    logger.info("[CALLBACK] Step 1 — /callback hit by Microsoft redirect")
    logger.info("[CALLBACK]          state in request : %s", request.args.get("state"))
    logger.info("[CALLBACK]          state in session : %s", session.get("auth_state"))

    # Validate state to prevent CSRF
    if request.args.get("state") != session.get("auth_state"):
        logger.error("[CALLBACK] CSRF check FAILED — state mismatch")
        return "State mismatch — possible CSRF.", 400
    logger.info("[CALLBACK] Step 2 — CSRF state validation passed")

    if "error" in request.args:
        logger.error("[CALLBACK] Azure AD returned error: %s — %s",
            request.args.get("error"), request.args.get("error_description"))
        return f"Login error: {request.args['error_description']}", 400, {"Content-Type": "text/plain; charset=utf-8"}

    logger.info("[CALLBACK] Step 3 — Authorization code received from Azure AD")
    logger.info("[CALLBACK] Step 4 — Exchanging authorization code for tokens via MSAL")
    cca = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET,
    )
    result = cca.acquire_token_by_authorization_code(
        request.args["code"],
        scopes=SCOPE,
        redirect_uri=url_for("auth_callback", _external=True),
    )

    if "error" in result:
        logger.error("[CALLBACK] Token exchange failed: %s — %s",
            result.get("error"), result.get("error_description"))
        return f"Token error: {result.get('error_description')}", 400

    logger.info("[CALLBACK] Step 5 — Token exchange successful")
    logger.info("[CALLBACK] Step 6 — Extracting ID token claims")
    session["user"] = result.get("id_token_claims")

    logger.info("[CALLBACK] Step 7 — ID token claims stored in session")
    logger.info("[CALLBACK]          name               : %s", session["user"].get("name"))
    logger.info("[CALLBACK]          preferred_username : %s", session["user"].get("preferred_username"))
    logger.info("[CALLBACK]          roles              : %s", session["user"].get("roles"))
    logger.info("[CALLBACK]          tenant id          : %s", session["user"].get("tid"))
    logger.debug("[CALLBACK] Full ID token claims: %s", json.dumps(session["user"], indent=2))

    next_url = session.pop("next", url_for("dashboard"))
    logger.info("[CALLBACK] Step 8 — Redirecting user to: %s", next_url)
    return redirect(next_url)


@app.route("/logout")
def logout():
    user = session.get("user", {})
    logger.info("[LOGOUT] Step 1 — /logout hit by user: %s", user.get("preferred_username"))
    session.clear()
    logger.info("[LOGOUT] Step 2 — Session cleared")
    logout_url = (
        f"{AUTHORITY}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={url_for('login', _external=True)}"
    )
    logger.info("[LOGOUT] Step 3 — Redirecting to Microsoft logout endpoint")
    logger.debug("[LOGOUT] Full logout URL: %s", logout_url)
    return redirect(logout_url)


# ── Public pages ──────────────────────────────────────────────────────────────
@app.route("/")
@login_required
def home():
    return render_template("home.html", user=session.get("user"))


@app.route("/about")
@login_required
def about():
    return render_template("about.html", user=session.get("user"))


# ── Protected pages ───────────────────────────────────────────────────────────
@app.route("/dashboard")
@role_required("admin")
def dashboard():
    return render_template("dashboard.html", user=session["user"])


@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=session["user"])


if __name__ == "__main__":
    app.run(host="localhost", port=3000, debug=True)
