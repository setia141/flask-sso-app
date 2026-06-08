import os
import sys
import pytest

os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("AZURE_CLIENT_ID", "test-client-id")
os.environ.setdefault("AZURE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("AZURE_TENANT_ID", "test-tenant-id")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    with app.test_client() as c:
        yield c


def test_callback_state_mismatch_returns_400(client):
    """Happy path: CSRF check rejects mismatched state."""
    response = client.get("/callback?state=bad&code=abc")
    assert response.status_code == 400
    assert b"State mismatch" in response.data


def test_callback_error_description_is_reflected(client):
    """Fix scenario: error_description from request is reflected in response body.

    Before the fix this response is HTML — any injected script would execute.
    After the fix the content-type must be text/plain (or the value escaped).
    """
    with client.session_transaction() as sess:
        sess["auth_state"] = "same-state"

    payload = "<script>alert(1)</script>"
    response = client.get(
        f"/callback?state=same-state&error=access_denied&error_description={payload}"
    )
    assert response.status_code == 400
    content_type = response.content_type
    data = response.data.decode()
    # After fix: either content_type is text/plain OR the script tag is escaped
    is_plain = "text/plain" in content_type
    is_escaped = "<script>" not in data
    assert is_plain or is_escaped, (
        f"XSS not mitigated: content_type={content_type!r}, body={data!r}"
    )
