from app.models import AdminAuditLog
from tests.conftest import post_csrf


def _setup_form(make_scope, make_category, make_form):
    scope_id = make_scope(name="AR")
    category_id = make_category(scope_id)
    form_id = make_form(scope_id, category_id=category_id)
    return scope_id, category_id, form_id


def test_dashboard_counts_tickets(admin_client, admin_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    make_ticket(form_id, created_by=admin_user, status="Pending")
    make_ticket(form_id, created_by=admin_user, status="Rejected")

    resp = admin_client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert b"2" in resp.data  # total_tickets somewhere on the page


def test_all_tickets_page_lists_tickets(admin_client, admin_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    make_ticket(form_id, created_by=admin_user, subject="Findable Ticket")
    resp = admin_client.get("/admin/tickets")
    assert resp.status_code == 200
    assert b"Findable Ticket" in resp.data


def test_export_all_tickets_xlsx_and_logs_audit(app, admin_client, admin_user, make_scope, make_category, make_form, make_ticket):
    _, _, form_id = _setup_form(make_scope, make_category, make_form)
    make_ticket(form_id, created_by=admin_user)

    resp = admin_client.get("/admin/tickets/export")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    with app.app_context():
        assert AdminAuditLog.query.filter_by(action="EXPORT_TRIGGERED").count() == 1


def test_audit_log_records_admin_actions(app, admin_client, make_scope):
    post_csrf(admin_client, "/admin/scopes/create", data={"name": "NewScope"}, follow_redirects=True)
    resp = admin_client.get("/admin/audit-log")
    assert resp.status_code == 200
    assert b"SCOPE_CREATED" in resp.data


def test_export_audit_returns_xlsx(admin_client, make_scope):
    post_csrf(admin_client, "/admin/scopes/create", data={"name": "AuditedScope"}, follow_redirects=True)
    resp = admin_client.get("/admin/export-audit")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
