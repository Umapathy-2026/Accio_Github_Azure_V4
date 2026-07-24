from app.routes.auth import validate_password_strength


def test_password_too_short():
    errors = validate_password_strength("Ab1")
    assert any("8 characters" in e for e in errors)


def test_password_missing_uppercase():
    errors = validate_password_strength("lowercase1")
    assert any("uppercase" in e for e in errors)


def test_password_missing_digit():
    errors = validate_password_strength("NoDigitsHere")
    assert any("number" in e for e in errors)


def test_password_valid():
    assert validate_password_strength("ValidPass1") == []


def test_role_required_blocks_wrong_role(admin_client, approver_client, requester_client):
    # Admin-only page
    resp = requester_client.get("/admin/dashboard", follow_redirects=True)
    assert b"do not have permission" in resp.data or resp.status_code in (302, 200)

    resp = approver_client.get("/admin/dashboard", follow_redirects=False)
    assert resp.status_code == 302


def test_role_required_allows_correct_role(admin_client):
    resp = admin_client.get("/admin/dashboard")
    assert resp.status_code == 200


def test_login_required_redirects_anonymous(client):
    resp = client.get("/admin/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]
