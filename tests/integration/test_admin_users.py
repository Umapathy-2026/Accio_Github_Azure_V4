from datetime import datetime, timezone, timedelta

from app import db
from app.models import User, Ticket
from tests.conftest import post_csrf


def test_create_user_happy_path(app, admin_client):
    resp = post_csrf(admin_client, "/admin/users", data={
        "display_name": "Jane Doe",
        "email": "jane@test.com",
        "password": "StrongPass1",
        "role": "user",
    }, follow_redirects=True)
    assert b"created successfully" in resp.data
    with app.app_context():
        user = User.query.filter_by(email="jane@test.com").first()
        assert user is not None
        assert user.role == "user"


def test_create_user_missing_fields_rejected(admin_client):
    resp = post_csrf(admin_client, "/admin/users", data={
        "display_name": "",
        "email": "",
        "password": "",
    }, follow_redirects=True)
    assert b"required" in resp.data


def test_create_user_duplicate_email_rejected(admin_client, make_user):
    make_user("existing@test.com")
    resp = post_csrf(admin_client, "/admin/users", data={
        "display_name": "Dup",
        "email": "existing@test.com",
        "password": "StrongPass1",
        "role": "user",
    }, follow_redirects=True)
    assert b"already exists" in resp.data


def test_create_user_weak_password_rejected(admin_client):
    resp = post_csrf(admin_client, "/admin/users", data={
        "display_name": "Weak",
        "email": "weak@test.com",
        "password": "weak",
        "role": "user",
    }, follow_redirects=True)
    assert b"8 characters" in resp.data or b"uppercase" in resp.data


def test_create_user_with_scopes(app, admin_client, make_scope):
    ar_id = make_scope(name="AR")
    resp = post_csrf(admin_client, "/admin/users", data={
        "display_name": "Scoped",
        "email": "scoped@test.com",
        "password": "StrongPass1",
        "role": "user",
        "scope_ids": [str(ar_id)],
    }, follow_redirects=True)
    assert b"created successfully" in resp.data
    with app.app_context():
        user = User.query.filter_by(email="scoped@test.com").first()
        assert [s.name for s in user.scopes] == ["AR"]


def test_edit_user_updates_fields(app, admin_client, make_user):
    user_id = make_user("editme@test.com", role="user")
    resp = post_csrf(admin_client, f"/admin/users/{user_id}/edit", data={
        "display_name": "Edited Name",
        "role": "approver",
        "is_active": "on",
    }, follow_redirects=True)
    assert b"updated successfully" in resp.data
    with app.app_context():
        user = User.query.get(user_id)
        assert user.display_name == "Edited Name"
        assert user.role == "approver"


def test_unlock_user_clears_lockout(app, admin_client, make_user):
    user_id = make_user("locked@test.com")
    with app.app_context():
        user = User.query.get(user_id)
        user.failed_attempts = 5
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        db.session.commit()

    resp = post_csrf(admin_client, f"/admin/users/{user_id}/unlock", follow_redirects=True)
    assert b"has been unlocked" in resp.data
    with app.app_context():
        user = User.query.get(user_id)
        assert user.failed_attempts == 0
        assert user.locked_until is None


def test_deactivate_check_reports_open_tickets(app, admin_client, make_user, make_scope, make_category, make_form, make_ticket):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    form_id = make_form(scope_id, category_id=cat_id)
    approver_id = make_user("appr_dc@test.com", role="approver")
    requester_id = make_user("req_dc@test.com", role="user", approver_id=approver_id)
    make_ticket(form_id, created_by=requester_id, assigned_to=approver_id, status="Pending")

    resp = admin_client.get(f"/admin/users/{requester_id}/deactivate-check")
    data = resp.get_json()
    assert data["has_dependencies"] is True
    assert data["created_count"] == 1


def test_deactivate_user_sets_inactive(app, admin_client, make_user):
    user_id = make_user("todeactivate@test.com", role="user")
    resp = post_csrf(admin_client, f"/admin/users/{user_id}/deactivate", data={}, follow_redirects=True)
    assert b"deactivated" in resp.data
    with app.app_context():
        assert User.query.get(user_id).is_active is False


def test_deactivate_approver_requires_reassignment_target(app, admin_client, make_user):
    approver_id = make_user("appr_deact@test.com", role="approver")
    make_user("sub@test.com", role="user", approver_id=approver_id)

    resp = post_csrf(admin_client, f"/admin/users/{approver_id}/deactivate", data={}, follow_redirects=True)
    assert b"must select a new approver" in resp.data
    with app.app_context():
        assert User.query.get(approver_id).is_active is True
