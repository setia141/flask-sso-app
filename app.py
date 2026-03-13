"""
Flask app with Azure AD SSO + Role-Based Access Control (RBAC).

Public pages    : /  (home), /about
Protected pages : /profile   — any logged-in user (admin, user, viewer)
                  /dashboard — admin only
"""
import os
import uuid
import msal
from functools import wraps
from flask import (
    Flask, render_template, redirect, request,
    session, url_for, abort
)
from flask_session import Session
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# Store sessions on the filesystem so the cookie only holds a session ID
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(os.path.dirname(__file__), ".flask_session")
app.config["SESSION_PERMANENT"] = False
Session(app)

# ── Azure AD config ──────────────────────────────────────────────────────────
CLIENT_ID     = os.environ["AZURE_CLIENT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]
TENANT_ID     = os.environ["AZURE_TENANT_ID"]

AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_PATH = "/callback"
SCOPE         = ["User.Read"]          # MS Graph — basic profile info


def _build_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )


def _get_token_from_cache():
    """Return a valid access token from session cache, or None."""
    cache = session.get("token_cache")
    if not cache:
        return None
    token_cache = msal.SerializableTokenCache()
    token_cache.deserialize(cache)
    cca = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        token_cache=token_cache,
    )
    accounts = cca.get_accounts()
    if not accounts:
        return None
    result = cca.acquire_token_silent(SCOPE, account=accounts[0])
    session["token_cache"] = token_cache.serialize()
    return result


# ── Auth decorators ───────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            session["next"] = request.url
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Decorator that requires the user to have one of the specified Azure AD App Roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("user"):
                session["next"] = request.url
                return redirect(url_for("login"))
            user_roles = session["user"].get("roles", [])
            if not any(r in user_roles for r in roles):
                return render_template("access_denied.html", user=session["user"], required_roles=roles), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route("/login")
def login():
    state = str(uuid.uuid4())
    session["auth_state"] = state
    auth_url = _build_msal_app().get_authorization_request_url(
        SCOPE,
        state=state,
        redirect_uri=url_for("auth_callback", _external=True),
    )
    return redirect(auth_url)


@app.route(REDIRECT_PATH)
def auth_callback():
    # Validate state to prevent CSRF
    if request.args.get("state") != session.get("auth_state"):
        return "State mismatch — possible CSRF.", 400

    if "error" in request.args:
        return f"Login error: {request.args['error_description']}", 400

    token_cache = msal.SerializableTokenCache()
    cca = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        token_cache=token_cache,
    )
    result = cca.acquire_token_by_authorization_code(
        request.args["code"],
        scopes=SCOPE,
        redirect_uri=url_for("auth_callback", _external=True),
    )

    if "error" in result:
        return f"Token error: {result.get('error_description')}", 400

    session["user"] = result.get("id_token_claims")
    session["token_cache"] = token_cache.serialize()

    next_url = session.pop("next", url_for("dashboard"))
    return redirect(next_url)


@app.route("/logout")
def logout():
    session.clear()
    logout_url = (
        f"{AUTHORITY}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={url_for('home', _external=True)}"
    )
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
