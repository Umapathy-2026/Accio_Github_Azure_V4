from unittest.mock import patch, MagicMock

from app import db
from app.models import User
from tests.conftest import get_csrf_token, post_csrf


def test_login_success(client, make_user):
    make_user("user@test.com", role="user")
    token = get_csrf_token(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": "user@test.com", "password": "Password1"},
        headers={"X-CSRFToken": token},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Dashboard" in resp.data or b"dashboard" in resp.data.lower()


def test_login_wrong_password(client, make_user):
    make_user("user2@test.com", role="user")
    token = get_csrf_token(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": "user2@test.com", "password": "WrongPass1"},
        headers={"X-CSRFToken": token},
        follow_redirects=True,
    )
    assert b"Invalid email or password" in resp.data


def test_login_missing_fields(client):
    token = get_csrf_token(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": "", "password": ""},
        headers={"X-CSRFToken": token},
        follow_redirects=True,
    )
    assert b"enter your email and password" in resp.data


def test_login_requires_csrf_token(client, make_user):
    make_user("nocsrf@test.com")
    client.get("/auth/login")  # establish session
    resp = client.post("/auth/login", data={"email": "nocsrf@test.com", "password": "Password1"})
    assert resp.status_code == 400  # CSRF failure


def test_account_locks_after_three_failed_attempts(app, client, make_user):
    make_user("locktest@test.com", role="user")
    for _ in range(3):
        token = get_csrf_token(client, "/auth/login")
        client.post(
            "/auth/login",
            data={"email": "locktest@test.com", "password": "WrongPass1"},
            headers={"X-CSRFToken": token},
        )
    with app.app_context():
        user = User.query.filter_by(email="locktest@test.com").first()
        assert user.failed_attempts >= 3
        assert user.locked_until is not None

    # Even the correct password is now rejected
    token = get_csrf_token(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": "locktest@test.com", "password": "Password1"},
        headers={"X-CSRFToken": token},
        follow_redirects=True,
    )
    assert b"account is locked" in resp.data.lower()


def test_inactive_user_cannot_login(client, make_user):
    make_user("inactive@test.com", is_active=False)
    token = get_csrf_token(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": "inactive@test.com", "password": "Password1"},
        headers={"X-CSRFToken": token},
        follow_redirects=True,
    )
    assert b"Invalid email or password" in resp.data


def test_must_change_password_redirects_after_login(client, make_user):
    make_user("mustchange@test.com", must_change_password=True)
    token = get_csrf_token(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": "mustchange@test.com", "password": "Password1"},
        headers={"X-CSRFToken": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/auth/change-password" in resp.headers["Location"]


def test_force_change_password_flow(client, make_user):
    make_user("forced@test.com", must_change_password=True)
    token = get_csrf_token(client, "/auth/login")
    client.post(
        "/auth/login",
        data={"email": "forced@test.com", "password": "Password1"},
        headers={"X-CSRFToken": token},
    )
    resp = post_csrf(client, "/auth/change-password", data={
        "new_password": "NewPassword2",
        "confirm_password": "NewPassword2",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Password changed successfully" in resp.data

    # Logging back in with the new password now works without a forced redirect
    client.get("/auth/logout")
    token = get_csrf_token(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": "forced@test.com", "password": "NewPassword2"},
        headers={"X-CSRFToken": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/auth/change-password" not in resp.headers["Location"]


def test_forgot_password_sends_reset_token(app, client, make_user):
    make_user("forgot@test.com")
    resp = post_csrf(client, "/auth/forgot-password", data={"email": "forgot@test.com"}, follow_redirects=True)
    assert b"a password reset link has been sent" in resp.data
    with app.app_context():
        user = User.query.filter_by(email="forgot@test.com").first()
        assert user.reset_token is not None
        assert user.reset_token_expiry is not None


def test_forgot_password_unknown_email_does_not_leak(client):
    resp = post_csrf(client, "/auth/forgot-password", data={"email": "nobody@test.com"}, follow_redirects=True)
    # Same generic message regardless of whether the account exists
    assert b"a password reset link has been sent" in resp.data


def test_reset_password_with_valid_token(app, client, make_user):
    import hashlib
    import secrets
    from datetime import datetime, timezone, timedelta

    user_id = make_user("reset@test.com")
    raw_token = secrets.token_urlsafe(48)
    with app.app_context():
        user = User.query.get(user_id)
        user.reset_token = hashlib.sha256(raw_token.encode()).hexdigest()
        user.reset_token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        db.session.commit()

    resp = post_csrf(client, f"/auth/reset-password/{raw_token}", data={
        "password": "BrandNew1",
        "confirm_password": "BrandNew1",
    }, follow_redirects=True)
    assert b"Password reset successfully" in resp.data

    with app.app_context():
        user = User.query.get(user_id)
        assert user.reset_token is None
        from werkzeug.security import check_password_hash
        assert check_password_hash(user.password_hash, "BrandNew1")


def test_reset_password_with_invalid_token(client):
    resp = client.get("/auth/reset-password/not-a-real-token", follow_redirects=True)
    assert b"invalid or has expired" in resp.data


def test_logout_clears_session(client, make_user):
    make_user("logout@test.com")
    token = get_csrf_token(client, "/auth/login")
    client.post(
        "/auth/login",
        data={"email": "logout@test.com", "password": "Password1"},
        headers={"X-CSRFToken": token},
    )
    resp = client.get("/admin/dashboard", follow_redirects=False)
    # Not an admin, but authenticated -> role_required redirect, not login redirect
    client.get("/auth/logout")
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


# ── Entra SSO (mocked MSAL) ───────────────────────────────────────────────

def test_entra_login_not_configured_falls_back(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "ENTRA_CLIENT_ID", "")
    resp = client.get("/auth/entra/login", follow_redirects=True)
    assert b"not configured" in resp.data


def test_entra_login_redirects_to_microsoft(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "ENTRA_CLIENT_ID", "fake-client-id")
    monkeypatch.setitem(app.config, "ENTRA_TENANT_ID", "fake-tenant")
    monkeypatch.setitem(app.config, "ENTRA_REDIRECT_URI", "http://localhost/auth/entra/callback")

    fake_cca = MagicMock()
    fake_cca.get_authorization_request_url.return_value = "https://login.microsoftonline.com/fake-auth-url"
    with patch("app.routes.auth._build_msal_app", return_value=fake_cca):
        resp = client.get("/auth/entra/login", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://login.microsoftonline.com/fake-auth-url"


def test_entra_callback_jit_provisions_new_user(app, client):
    with client.session_transaction() as sess:
        sess["entra_state"] = "test-state-123"

    fake_cca = MagicMock()
    fake_cca.acquire_token_by_authorization_code.return_value = {
        "id_token_claims": {
            "oid": "entra-oid-abc",
            "preferred_username": "newperson@company.com",
            "name": "New Person",
        }
    }
    with patch("app.routes.auth._build_msal_app", return_value=fake_cca):
        resp = client.get(
            "/auth/entra/callback?state=test-state-123&code=authcode",
            follow_redirects=True,
        )
    assert resp.status_code == 200
    with app.app_context():
        user = User.query.filter_by(entra_oid="entra-oid-abc").first()
        assert user is not None
        assert user.email == "newperson@company.com"
        assert user.role == "user"


def test_entra_callback_links_existing_local_user_by_email(app, client, make_user):
    make_user("linkme@company.com", role="approver")
    with client.session_transaction() as sess:
        sess["entra_state"] = "state-456"

    fake_cca = MagicMock()
    fake_cca.acquire_token_by_authorization_code.return_value = {
        "id_token_claims": {
            "oid": "entra-oid-xyz",
            "preferred_username": "linkme@company.com",
            "name": "Link Me",
        }
    }
    with patch("app.routes.auth._build_msal_app", return_value=fake_cca):
        client.get("/auth/entra/callback?state=state-456&code=authcode", follow_redirects=True)

    with app.app_context():
        user = User.query.filter_by(email="linkme@company.com").first()
        assert user.entra_oid == "entra-oid-xyz"
        assert user.role == "approver"  # existing role preserved, not overwritten


def test_entra_callback_rejects_invalid_state(client):
    with client.session_transaction() as sess:
        sess["entra_state"] = "expected-state"
    resp = client.get(
        "/auth/entra/callback?state=wrong-state&code=authcode",
        follow_redirects=True,
    )
    assert b"invalid state" in resp.data.lower()
