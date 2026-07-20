import io

from app import db
from app.models import Ticket, User
from tests.conftest import post_csrf


def _setup_form(make_scope, make_category, make_form, name="Refund Request"):
    scope_id = make_scope(name="AR")
    category_id = make_category(scope_id, name="Billing")
    form_id = make_form(scope_id, category_id=category_id, name=name)
    return scope_id, category_id, form_id


def test_new_ticket_page_loads(requester_client):
    resp = requester_client.get("/ticket/new")
    assert resp.status_code == 200


def test_new_ticket_requires_approver_assigned(app, client, make_user):
    # user with no approver_id
    make_user("noapprover@test.com", role="user")
    from tests.conftest import get_csrf_token
    token = get_csrf_token(client, "/auth/login")
    client.post("/auth/login", data={"email": "noapprover@test.com", "password": "Password1"},
                headers={"X-CSRFToken": token})
    resp = post_csrf(client, "/ticket/new", data={"form_id": "1"}, follow_redirects=True)
    assert b"do not have an approver assigned" in resp.data


def test_categories_api_filters_by_scope(requester_client, make_scope, make_category):
    ar_id = make_scope(name="AR")
    gl_id = make_scope(name="GL")
    make_category(ar_id, name="Billing")
    make_category(gl_id, name="Journal Entries")

    resp = requester_client.get(f"/requester/api/categories?scope_id={ar_id}")
    data = resp.get_json()
    assert [c["name"] for c in data["categories"]] == ["Billing"]


def test_forms_api_returns_only_active_undeleted_in_scope_and_category(
    requester_client, make_scope, make_category, make_form
):
    scope_id = make_scope(name="AR")
    cat_id = make_category(scope_id, name="Billing")
    active_id = make_form(scope_id, category_id=cat_id, name="Active Form")
    make_form(scope_id, category_id=cat_id, name="Inactive Form", is_active=False)

    resp = requester_client.get(f"/requester/api/forms?scope_id={scope_id}&category_id={cat_id}")
    data = resp.get_json()
    names = [f["name"] for f in data["forms"]]
    assert names == ["Active Form"]


def test_create_ticket_happy_path(app, requester_client, requester_user, make_scope, make_category, make_form):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)

    resp = post_csrf(requester_client, "/ticket/new", data={
        "form_id": str(form_id),
        "subject": "My refund issue",
        "description": "Please refund my invoice",
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"created successfully" in resp.data

    with app.app_context():
        ticket = Ticket.query.filter_by(created_by=requester_user).first()
        assert ticket is not None
        assert ticket.subject == "My refund issue"
        assert ticket.current_status == "Pending"
        assert ticket.scope == "AR"


def test_create_ticket_missing_required_field_rejected(requester_client, make_scope, make_category, make_form):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    resp = post_csrf(requester_client, "/ticket/new", data={
        "form_id": str(form_id),
        # subject omitted -> required
    }, follow_redirects=True)
    assert b"Subject is required" in resp.data or b"required" in resp.data


def test_create_ticket_inactive_form_rejected(requester_client, make_scope, make_category, make_form):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    with requester_client.application.app_context():
        from app.models import IssueForm
        f = IssueForm.query.get(form_id)
        f.is_active = False
        db.session.commit()

    resp = post_csrf(requester_client, "/ticket/new", data={
        "form_id": str(form_id),
        "subject": "Should fail",
    }, follow_redirects=True)
    assert b"not available" in resp.data


def test_create_ticket_with_attachment_and_download(app, requester_client, requester_user, make_scope, make_category, make_form):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)

    from tests.conftest import get_csrf_token
    token = get_csrf_token(requester_client)
    resp = requester_client.post(
        "/ticket/new",
        data={
            "form_id": str(form_id),
            "subject": "With attachment",
            "attachment": (io.BytesIO(b"%PDF-1.4 fake pdf"), "proof.pdf"),
        },
        headers={"X-CSRFToken": token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"created successfully" in resp.data

    with app.app_context():
        ticket = Ticket.query.filter_by(subject="With attachment").first()
        assert ticket.attachment_name == "proof.pdf"
        ticket_id = ticket.id

    dl = requester_client.get(f"/attachment/{ticket_id}")
    assert dl.status_code == 200


def test_download_attachment_forbidden_for_unrelated_user(app, client, make_user, make_scope, make_category, make_form, requester_client, requester_user):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    from tests.conftest import get_csrf_token
    token = get_csrf_token(requester_client)
    requester_client.post(
        "/ticket/new",
        data={
            "form_id": str(form_id),
            "subject": "Private ticket",
            "attachment": (io.BytesIO(b"data"), "secret.pdf"),
        },
        headers={"X-CSRFToken": token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    with app.app_context():
        ticket_id = Ticket.query.filter_by(subject="Private ticket").first().id

    other_id = make_user("stranger@test.com", role="user")
    o_token = get_csrf_token(client, "/auth/login")
    client.post("/auth/login", data={"email": "stranger@test.com", "password": "Password1"},
                headers={"X-CSRFToken": o_token})
    resp = client.get(f"/attachment/{ticket_id}")
    assert resp.status_code == 403


def test_ticket_detail_owner_can_view(app, requester_client, requester_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    ticket_id = make_ticket(form_id, created_by=requester_user)
    resp = requester_client.get(f"/ticket/{ticket_id}")
    assert resp.status_code == 200


def test_ticket_detail_other_user_forbidden(client, make_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    owner_id = make_user("owner@test.com", role="user")
    ticket_id = make_ticket(form_id, created_by=owner_id)

    make_user("other@test.com", role="user")
    from tests.conftest import get_csrf_token
    token = get_csrf_token(client, "/auth/login")
    client.post("/auth/login", data={"email": "other@test.com", "password": "Password1"},
                headers={"X-CSRFToken": token})
    resp = client.get(f"/ticket/{ticket_id}", follow_redirects=True)
    assert b"do not have permission" in resp.data


def test_clarify_ticket_flow(app, requester_client, requester_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    ticket_id = make_ticket(form_id, created_by=requester_user, status="Needs Clarification")

    resp = post_csrf(requester_client, f"/ticket/{ticket_id}/clarify", data={
        "clarification": "Here is the extra info you asked for.",
    }, follow_redirects=True)
    assert b"Clarification submitted successfully" in resp.data

    with app.app_context():
        ticket = Ticket.query.get(ticket_id)
        assert ticket.current_status == "Under Review"
        assert ticket.payload.get("__clarification__") == "Here is the extra info you asked for."


def test_clarify_ticket_wrong_status_rejected(requester_client, requester_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    ticket_id = make_ticket(form_id, created_by=requester_user, status="Pending")

    resp = post_csrf(requester_client, f"/ticket/{ticket_id}/clarify", data={
        "clarification": "Info",
    }, follow_redirects=True)
    assert b"does not need clarification" in resp.data


def test_export_ticket_returns_xlsx(requester_client, requester_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    ticket_id = make_ticket(form_id, created_by=requester_user)
    resp = requester_client.get(f"/ticket/{ticket_id}/export")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_notifications_page_marks_read(app, requester_client, requester_user):
    from app.models import Notification
    with app.app_context():
        db.session.add(Notification(user_id=requester_user, title="Hi", message="msg", is_read=False))
        db.session.commit()

    resp = requester_client.get("/notifications")
    assert resp.status_code == 200
    with app.app_context():
        notif = Notification.query.filter_by(user_id=requester_user).first()
        assert notif.is_read is True
