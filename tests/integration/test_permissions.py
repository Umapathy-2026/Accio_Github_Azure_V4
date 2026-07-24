import pytest

ADMIN_ROUTES = ["/admin/dashboard", "/admin/tickets", "/admin/users", "/admin/forms", "/admin/scopes", "/admin/audit-log"]
APPROVER_ROUTES = ["/approver/queue", "/approver/history", "/approver/request-history"]
REQUESTER_ROUTES = ["/dashboard", "/ticket/new"]


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_requester_cannot_access_admin_routes(requester_client, route):
    resp = requester_client.get(route, follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin" not in resp.headers.get("Location", "") or resp.headers["Location"].endswith("/auth/login")


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_approver_cannot_access_admin_routes(approver_client, route):
    resp = approver_client.get(route, follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.parametrize("route", APPROVER_ROUTES)
def test_requester_cannot_access_approver_routes(requester_client, route):
    resp = requester_client.get(route, follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_admin_can_access_admin_routes(admin_client, route):
    resp = admin_client.get(route)
    assert resp.status_code == 200


@pytest.mark.parametrize("route", APPROVER_ROUTES)
def test_admin_can_access_approver_routes(admin_client, route):
    resp = admin_client.get(route)
    assert resp.status_code == 200


@pytest.mark.parametrize("route", APPROVER_ROUTES)
def test_approver_can_access_approver_routes(approver_client, route):
    resp = approver_client.get(route)
    assert resp.status_code == 200


@pytest.mark.parametrize("route", REQUESTER_ROUTES + ADMIN_ROUTES + APPROVER_ROUTES)
def test_anonymous_user_redirected_to_login(client, route):
    resp = client.get(route, follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


@pytest.mark.parametrize("route", REQUESTER_ROUTES)
def test_all_roles_can_access_requester_routes(admin_client, approver_client, requester_client, route):
    for c in (admin_client, approver_client, requester_client):
        resp = c.get(route)
        assert resp.status_code == 200
