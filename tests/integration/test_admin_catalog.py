from app import db
from app.models import Scope, Category, IssueForm
from tests.conftest import post_csrf, get_csrf_token


# ── Scopes ────────────────────────────────────────────────────────────────

def test_create_scope(app, admin_client):
    resp = post_csrf(admin_client, "/admin/scopes/create", data={"name": "GL"}, follow_redirects=True)
    assert b"created successfully" in resp.data
    with app.app_context():
        assert Scope.query.filter_by(name="GL").first() is not None


def test_create_scope_duplicate_case_insensitive_rejected(admin_client, make_scope):
    make_scope(name="AR")
    resp = post_csrf(admin_client, "/admin/scopes/create", data={"name": "ar"}, follow_redirects=True)
    assert b"already exists" in resp.data


def test_toggle_scope_blocked_when_active_forms_exist(app, admin_client, make_scope, make_category, make_form):
    scope_id = make_scope(name="AR")
    cat_id = make_category(scope_id)
    make_form(scope_id, category_id=cat_id, is_active=True)

    resp = post_csrf(admin_client, f"/admin/scopes/{scope_id}/toggle", follow_redirects=True)
    assert b"Deactivate those forms first" in resp.data
    with app.app_context():
        assert Scope.query.get(scope_id).is_active is True


def test_toggle_scope_succeeds_without_active_forms(app, admin_client, make_scope):
    scope_id = make_scope(name="GL")
    resp = post_csrf(admin_client, f"/admin/scopes/{scope_id}/toggle", follow_redirects=True)
    assert b"deactivated" in resp.data
    with app.app_context():
        assert Scope.query.get(scope_id).is_active is False


# ── Categories (recently-buggy area) ────────────────────────────────────

def test_create_category(app, admin_client, make_scope):
    scope_id = make_scope(name="AR")
    resp = post_csrf(admin_client, "/admin/categories/create", data={
        "name": "Billing", "scope_id": str(scope_id),
    }, follow_redirects=True)
    assert b"created successfully" in resp.data
    with app.app_context():
        assert Category.query.filter_by(name="Billing", scope_id=scope_id).first() is not None


def test_create_category_ajax_returns_json(admin_client, make_scope):
    scope_id = make_scope(name="AR")
    token = get_csrf_token(admin_client)
    resp = admin_client.post("/admin/categories/create", data={
        "name": "Journal", "scope_id": str(scope_id),
    }, headers={"X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest"})
    body = resp.get_json()
    assert body["success"] is True
    assert body["category"]["name"] == "Journal"


def test_create_category_duplicate_in_same_scope_rejected(admin_client, make_scope, make_category):
    scope_id = make_scope(name="AR")
    make_category(scope_id, name="Billing")
    resp = post_csrf(admin_client, "/admin/categories/create", data={
        "name": "billing", "scope_id": str(scope_id),
    }, follow_redirects=True)
    assert b"already exists" in resp.data


def test_create_category_missing_fields_rejected(admin_client):
    resp = post_csrf(admin_client, "/admin/categories/create", data={"name": ""}, follow_redirects=True)
    assert b"required" in resp.data


def test_edit_category_rename(app, admin_client, make_scope, make_category):
    scope_id = make_scope()
    cat_id = make_category(scope_id, name="Old Name")
    resp = post_csrf(admin_client, f"/admin/categories/{cat_id}/edit", data={"name": "New Name"}, follow_redirects=True)
    assert b"renamed" in resp.data
    with app.app_context():
        assert Category.query.get(cat_id).name == "New Name"


def test_edit_category_name_collision_rejected(admin_client, make_scope, make_category):
    scope_id = make_scope()
    make_category(scope_id, name="Billing")
    cat_id = make_category(scope_id, name="Other")
    resp = post_csrf(admin_client, f"/admin/categories/{cat_id}/edit", data={"name": "billing"}, follow_redirects=True)
    assert b"already exists" in resp.data


def test_toggle_category_blocked_when_active_forms_exist(app, admin_client, make_scope, make_category, make_form):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    make_form(scope_id, category_id=cat_id, is_active=True)

    resp = post_csrf(admin_client, f"/admin/categories/{cat_id}/toggle", follow_redirects=True)
    assert b"Deactivate those forms first" in resp.data
    with app.app_context():
        assert Category.query.get(cat_id).is_active is True


def test_delete_category_blocked_when_forms_reference_it(app, admin_client, make_scope, make_category, make_form):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    make_form(scope_id, category_id=cat_id)

    resp = post_csrf(admin_client, f"/admin/categories/{cat_id}/delete", follow_redirects=True)
    assert b"still linked to this category" in resp.data
    with app.app_context():
        assert Category.query.get(cat_id) is not None


def test_delete_category_succeeds_when_unreferenced(app, admin_client, make_scope, make_category):
    scope_id = make_scope()
    cat_id = make_category(scope_id, name="Unused")
    resp = post_csrf(admin_client, f"/admin/categories/{cat_id}/delete", follow_redirects=True)
    assert b"deleted" in resp.data
    with app.app_context():
        assert Category.query.get(cat_id) is None


def test_delete_category_detaches_soft_deleted_forms(app, admin_client, make_scope, make_category, make_form):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    form_id = make_form(scope_id, category_id=cat_id)
    with app.app_context():
        f = IssueForm.query.get(form_id)
        f.is_deleted = True
        f.is_active = False
        db.session.commit()

    resp = post_csrf(admin_client, f"/admin/categories/{cat_id}/delete", follow_redirects=True)
    assert b"deleted" in resp.data
    with app.app_context():
        assert Category.query.get(cat_id) is None
        assert IssueForm.query.get(form_id).category_id is None


def test_categories_list_json(admin_client, make_scope, make_category):
    scope_id = make_scope()
    make_category(scope_id, name="A")
    make_category(scope_id, name="B")
    resp = admin_client.get("/admin/categories/list")
    body = resp.get_json()
    names = sorted(c["name"] for c in body["categories"])
    assert names == ["A", "B"]


# ── Forms ────────────────────────────────────────────────────────────────

def test_create_form_requires_category(admin_client, make_scope):
    scope_id = make_scope()
    resp = post_csrf(admin_client, "/admin/forms/create", data={
        "form_name": "No Category Form", "scope_id": str(scope_id),
    }, follow_redirects=True)
    assert b"Category is required" in resp.data


def test_create_form_happy_path(app, admin_client, make_scope, make_category):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    resp = post_csrf(admin_client, "/admin/forms/create", data={
        "form_name": "New Issue Form", "scope_id": str(scope_id), "category_id": str(cat_id),
    }, follow_redirects=True)
    assert b"created successfully" in resp.data
    with app.app_context():
        form = IssueForm.query.filter_by(name="New Issue Form").first()
        assert form is not None
        field_ids = [f["id"] for f in form.fields]
        assert field_ids == ["subject", "description", "attachments"]


def test_create_form_duplicate_name_rejected(admin_client, make_scope, make_category, make_form):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    make_form(scope_id, category_id=cat_id, name="Existing Form")
    resp = post_csrf(admin_client, "/admin/forms/create", data={
        "form_name": "Existing Form", "scope_id": str(scope_id), "category_id": str(cat_id),
    }, follow_redirects=True)
    assert b"already exists" in resp.data


def test_toggle_form(app, admin_client, make_scope, make_category, make_form):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    form_id = make_form(scope_id, category_id=cat_id, is_active=True)
    resp = post_csrf(admin_client, f"/admin/forms/{form_id}/toggle", follow_redirects=True)
    assert b"deactivated" in resp.data
    with app.app_context():
        assert IssueForm.query.get(form_id).is_active is False


def test_edit_form_preserves_protected_fields(app, admin_client, make_scope, make_category, make_form):
    import json as _json
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    form_id = make_form(scope_id, category_id=cat_id)

    custom_fields = [{"id": "urgency", "label": "Urgency", "type": "dropdown", "required": True, "options": ["Low", "High"]}]
    resp = post_csrf(admin_client, f"/admin/forms/{form_id}/edit", data={
        "form_name": "Renamed Form",
        "fields_json": _json.dumps(custom_fields),
    }, follow_redirects=True)
    assert b"updated successfully" in resp.data
    with app.app_context():
        form = IssueForm.query.get(form_id)
        assert form.name == "Renamed Form"
        ids = [f["id"] for f in form.fields]
        assert ids == ["subject", "urgency", "description", "attachments"]


def test_delete_form_soft_deletes(app, admin_client, make_scope, make_category, make_form):
    scope_id = make_scope()
    cat_id = make_category(scope_id)
    form_id = make_form(scope_id, category_id=cat_id)
    resp = post_csrf(admin_client, f"/admin/forms/{form_id}/delete", follow_redirects=True)
    assert b"deleted" in resp.data
    with app.app_context():
        form = IssueForm.query.get(form_id)
        assert form.is_deleted is True
        assert form.is_active is False
