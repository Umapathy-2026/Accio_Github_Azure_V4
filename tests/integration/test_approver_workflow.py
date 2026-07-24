import json

from app import db
from app.models import Ticket, ApprovalLog, Notification
from tests.conftest import post_csrf


def _setup_form(make_scope, make_category, make_form, scope_name="AR"):
    scope_id = make_scope(name=scope_name)
    category_id = make_category(scope_id, name="Billing")
    form_id = make_form(scope_id, category_id=category_id, name="Refund Request")
    return scope_id, category_id, form_id


def test_queue_redirects_to_first_active_scope(approver_client, make_scope):
    make_scope(name="AR")
    resp = approver_client.get("/approver/queue", follow_redirects=False)
    assert resp.status_code == 302
    assert "/approver/queue/AR" in resp.headers["Location"]


def test_queue_dynamic_lists_only_assigned_open_tickets(
    app, approver_client, approver_user, make_scope, make_category, make_form, make_ticket, make_user
):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    other_approver = make_user("other_appr@test.com", role="approver")

    mine_pending = make_ticket(form_id, created_by=approver_user, assigned_to=approver_user,
                               subject="Mine Pending", status="Pending")
    make_ticket(form_id, created_by=approver_user, assigned_to=other_approver,
               subject="Not Mine", status="Pending")
    make_ticket(form_id, created_by=approver_user, assigned_to=approver_user,
               subject="Mine Approved Already", status="Sent to Fulfilment")

    resp = approver_client.get("/approver/queue/AR")
    assert resp.status_code == 200
    assert b"Mine Pending" in resp.data
    assert b"Not Mine" not in resp.data
    assert b"Mine Approved Already" not in resp.data


def test_approve_ticket_requires_comment(app, approver_client, approver_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    ticket_id = make_ticket(form_id, created_by=approver_user, assigned_to=approver_user)

    resp = post_csrf(approver_client, f"/approver/ticket/{ticket_id}/approve", data={}, follow_redirects=True)
    assert b"provide a comment" in resp.data
    with app.app_context():
        assert Ticket.query.get(ticket_id).current_status == "Pending"


def test_approve_ticket_success_sends_to_fulfilment(app, approver_client, approver_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    ticket_id = make_ticket(form_id, created_by=approver_user, assigned_to=approver_user)

    resp = post_csrf(approver_client, f"/approver/ticket/{ticket_id}/approve",
                     data={"comment": "Looks good"}, follow_redirects=True)
    assert b"approved and sent to fulfilment" in resp.data
    with app.app_context():
        ticket = Ticket.query.get(ticket_id)
        assert ticket.current_status == "Sent to Fulfilment"
        actions = [l.action for l in ApprovalLog.query.filter_by(ticket_id=ticket_id).all()]
        assert "Approved" in actions
        assert "Sent to Fulfilment" in actions
        assert Notification.query.filter_by(user_id=ticket.created_by).count() == 1


def test_reject_ticket_requires_comment_and_updates_status(app, approver_client, approver_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    ticket_id = make_ticket(form_id, created_by=approver_user, assigned_to=approver_user)

    resp = post_csrf(approver_client, f"/approver/ticket/{ticket_id}/reject", data={}, follow_redirects=True)
    assert b"provide a reason" in resp.data

    resp = post_csrf(approver_client, f"/approver/ticket/{ticket_id}/reject",
                     data={"comment": "Missing info"}, follow_redirects=True)
    assert b"rejected" in resp.data
    with app.app_context():
        assert Ticket.query.get(ticket_id).current_status == "Rejected"


def test_send_back_ticket_sets_needs_clarification(app, approver_client, approver_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    ticket_id = make_ticket(form_id, created_by=approver_user, assigned_to=approver_user)

    resp = post_csrf(approver_client, f"/approver/ticket/{ticket_id}/send-back",
                     data={"comment": "Need more detail"}, follow_redirects=True)
    assert b"sent back for clarification" in resp.data
    with app.app_context():
        assert Ticket.query.get(ticket_id).current_status == "Needs Clarification"


def test_ticket_action_rejected_when_not_assigned_to_approver(app, approver_client, make_scope, make_category, make_form, make_ticket, make_user):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    other_approver = make_user("someone_else@test.com", role="approver")
    ticket_id = make_ticket(form_id, created_by=other_approver, assigned_to=other_approver)

    resp = post_csrf(approver_client, f"/approver/ticket/{ticket_id}/approve",
                     data={"comment": "Trying anyway"}, follow_redirects=True)
    assert b"not assigned to you" in resp.data
    with app.app_context():
        assert Ticket.query.get(ticket_id).current_status == "Pending"


def test_reassign_ticket(app, approver_client, approver_user, make_scope, make_category, make_form, make_ticket, make_user):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    new_approver = make_user("new_approver@test.com", role="approver")
    ticket_id = make_ticket(form_id, created_by=approver_user, assigned_to=approver_user)

    resp = post_csrf(approver_client, f"/approver/ticket/{ticket_id}/reassign", data={
        "new_assignee_id": str(new_approver),
        "comment": "Better fit for this",
    }, follow_redirects=True)
    assert b"reassigned" in resp.data
    with app.app_context():
        assert Ticket.query.get(ticket_id).assigned_to == new_approver


def test_reassign_ticket_invalid_target_rejected(app, approver_client, approver_user, make_scope, make_category, make_form, make_ticket, make_user):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    non_approver = make_user("plainuser@test.com", role="user")
    ticket_id = make_ticket(form_id, created_by=approver_user, assigned_to=approver_user)

    resp = post_csrf(approver_client, f"/approver/ticket/{ticket_id}/reassign", data={
        "new_assignee_id": str(non_approver),
        "comment": "oops",
    }, follow_redirects=True)
    assert b"Invalid approver selected" in resp.data


def test_bulk_action_approve(app, approver_client, approver_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    t1 = make_ticket(form_id, created_by=approver_user, assigned_to=approver_user, subject="B1")
    t2 = make_ticket(form_id, created_by=approver_user, assigned_to=approver_user, subject="B2")

    from tests.conftest import get_csrf_token
    token = get_csrf_token(approver_client)
    resp = approver_client.post(
        "/approver/bulk-action",
        data=json.dumps({"ticket_ids": [t1, t2], "action": "approve", "comment": "batch ok"}),
        headers={"X-CSRFToken": token, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["processed"] == 2
    with app.app_context():
        assert Ticket.query.get(t1).current_status == "Sent to Fulfilment"
        assert Ticket.query.get(t2).current_status == "Sent to Fulfilment"


def test_bulk_action_invalid_payload(approver_client):
    from tests.conftest import get_csrf_token
    token = get_csrf_token(approver_client)
    resp = approver_client.post(
        "/approver/bulk-action",
        data=json.dumps({"ticket_ids": [], "action": "approve"}),
        headers={"X-CSRFToken": token, "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_approval_history_export_xlsx(approver_client, approver_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    make_ticket(form_id, created_by=approver_user, assigned_to=approver_user, status="Sent to Fulfilment")
    resp = approver_client.get("/approver/history/export")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
