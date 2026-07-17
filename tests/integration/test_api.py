from app.models import Notification
from app import db


def test_health_check_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["db"] == "connected"


def test_health_check_no_login_required(client):
    # /api/health is csrf-exempt and unauthenticated
    resp = client.get("/api/health")
    assert resp.status_code != 302


def test_form_fields_requires_login(client, make_scope, make_category, make_form):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    form_id = make_form(scope_id, category_id=cat_id)
    resp = client.get(f"/api/form-fields/{form_id}", follow_redirects=False)
    assert resp.status_code == 302


def test_form_fields_returns_normalized_fields(requester_client, make_scope, make_category, make_form):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    fields = [
        {"id": "subject", "label": "Subject", "type": "text", "required": True, "protected": True},
        {"id": "priority", "label": "Priority", "type": "dropdown", "required": True, "options": "Low,Medium,High"},
    ]
    form_id = make_form(scope_id, category_id=cat_id, fields=fields)

    resp = requester_client.get(f"/api/form-fields/{form_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    priority_field = next(f for f in body["fields"] if f["id"] == "priority")
    assert priority_field["options"] == ["Low", "Medium", "High"]


def test_form_fields_inactive_form_404(requester_client, make_scope, make_category, make_form):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    form_id = make_form(scope_id, category_id=cat_id, is_active=False)
    resp = requester_client.get(f"/api/form-fields/{form_id}")
    assert resp.status_code == 404


def test_notifications_list_and_unread_count(app, requester_client, requester_user):
    with app.app_context():
        db.session.add(Notification(user_id=requester_user, title="T1", message="M1", is_read=False))
        db.session.add(Notification(user_id=requester_user, title="T2", message="M2", is_read=True))
        db.session.commit()

    resp = requester_client.get("/api/notifications")
    body = resp.get_json()
    assert body["unread_count"] == 1
    assert len(body["notifications"]) == 2


def test_mark_all_notifications_read(app, requester_client, requester_user):
    from tests.conftest import get_csrf_token
    with app.app_context():
        db.session.add(Notification(user_id=requester_user, title="T", message="M", is_read=False))
        db.session.commit()

    token = get_csrf_token(requester_client)
    resp = requester_client.post("/api/notifications/mark-read", headers={"X-CSRFToken": token})
    assert resp.get_json()["success"] is True
    with app.app_context():
        assert Notification.query.filter_by(user_id=requester_user, is_read=False).count() == 0


def test_mark_one_notification_read_only_owned(app, requester_client, requester_user, make_user):
    from tests.conftest import get_csrf_token
    other_user = make_user("otherowner@test.com")
    with app.app_context():
        n = Notification(user_id=other_user, title="Not yours", message="M", is_read=False)
        db.session.add(n)
        db.session.commit()
        notif_id = n.id

    token = get_csrf_token(requester_client)
    resp = requester_client.post(f"/api/notifications/{notif_id}/read", headers={"X-CSRFToken": token})
    assert resp.get_json()["success"] is True  # route no-ops silently
    with app.app_context():
        assert Notification.query.get(notif_id).is_read is False  # untouched — not this user's
