import os
import re
import sys
import tempfile
import types

import pytest

# python-magic requires the native libmagic library. Where it's missing (e.g.
# this Windows dev box has no libmagic1 DLL) `magic.from_buffer()` doesn't
# raise ImportError/OSError as app.utils.storage.allowed_file() expects — it
# hangs. Stub the module before anything imports it so the suite stays
# hermetic and fast on every platform (CI included).
_fake_magic = types.ModuleType("magic")


def _fake_from_buffer(header, mime=True):
    if header.startswith(b"%PDF"):
        return "application/pdf"
    if header.startswith(b"\x89PNG"):
        return "image/png"
    if header[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if header[:2] == b"PK":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


_fake_magic.from_buffer = _fake_from_buffer
sys.modules["magic"] = _fake_magic

# Must happen before `app` (and therefore app/__init__.py's load_dotenv())
# is imported anywhere, so these values win over any local .env file.
TEST_SECRET_KEY = "test-secret-key-do-not-use-in-production"
_db_fd, _DB_PATH = tempfile.mkstemp(prefix="accio_test_", suffix=".db")
os.close(_db_fd)

os.environ["SECRET_KEY"] = TEST_SECRET_KEY
os.environ["FLASK_ENV"] = "testing"  # not 'development' -> seed_database() stays off
os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + _DB_PATH.replace(os.sep, "/")
os.environ["MAIL_DEV_MODE"] = "true"
os.environ.setdefault("ENTRA_CLIENT_ID", "")
os.environ.setdefault("ENTRA_CLIENT_SECRET", "")
os.environ.setdefault("ENTRA_TENANT_ID", "")
os.environ.setdefault("ENTRA_REDIRECT_URI", "http://localhost/auth/entra/callback")

from app import create_app, db as _db, limiter as _limiter  # noqa: E402
from app.models import (  # noqa: E402
    User,
    Scope,
    Category,
    IssueForm,
    Ticket,
    ApprovalLog,
    Notification,
    AdminAuditLog,
    UserScope,
)
from werkzeug.security import generate_password_hash  # noqa: E402


@pytest.fixture(scope="session")
def app():
    application = create_app(testing=True)
    application.config["TESTING"] = True
    # Flask-Limiter reads RATELIMIT_ENABLED only once, inside limiter.init_app()
    # (already called by create_app() above), so setting app.config afterward
    # has no effect. `limiter` is a module-level singleton shared across the
    # whole test process, so disable it directly to stop unrelated tests from
    # tripping each other's rate limits.
    _limiter.enabled = False

    yield application

    with application.app_context():
        _db.session.remove()
        _db.engine.dispose()
    # Best-effort: on Windows the OS may still hold a handle briefly after
    # dispose(); this is a disposable temp file, so a leftover is harmless.
    try:
        if os.path.exists(_DB_PATH):
            os.remove(_DB_PATH)
    except PermissionError:
        pass


@pytest.fixture(autouse=True)
def _clean_db(app):
    """Empty every table before each test, respecting FK order via the
    metadata's dependency-sorted table list (reversed for deletes)."""
    yield
    with app.app_context():
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


# ── CSRF helpers ─────────────────────────────────────────────────────────

def get_csrf_token(client, url="/auth/login"):
    # follow_redirects=True: an already-authenticated client GETting
    # /auth/login gets redirected to its dashboard rather than the login
    # form, but every page extends base.html (which carries the meta tag),
    # so following the redirect still lands somewhere the token is present.
    resp = client.get(url, follow_redirects=True)
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.get_data(as_text=True))
    assert match, f"CSRF token not found on {url}"
    return match.group(1)


def post_csrf(client, url, data=None, **kwargs):
    token = kwargs.pop("csrf_token", None) or get_csrf_token(client)
    headers = kwargs.pop("headers", {}) or {}
    headers["X-CSRFToken"] = token
    return client.post(url, data=data or {}, headers=headers, **kwargs)


@pytest.fixture
def csrf_post(client):
    """Bound helper: csrf_post(url, data) -> response, using `client`'s session."""
    def _do(url, data=None, **kwargs):
        return post_csrf(client, url, data=data, **kwargs)
    return _do


# ── Model factories ──────────────────────────────────────────────────────

@pytest.fixture
def make_scope(app):
    def _make(name="AR", is_active=True):
        with app.app_context():
            scope = Scope(name=name, is_active=is_active)
            _db.session.add(scope)
            _db.session.commit()
            return scope.id
    return _make


@pytest.fixture
def make_category(app):
    def _make(scope_id, name="Billing", is_active=True):
        with app.app_context():
            cat = Category(name=name, scope_id=scope_id, is_active=is_active)
            _db.session.add(cat)
            _db.session.commit()
            return cat.id
    return _make


@pytest.fixture
def make_form(app):
    def _make(scope_id, category_id=None, name="Refund Request", is_active=True, fields=None):
        from app.models import DEFAULT_FORM_FIELDS
        from copy import deepcopy
        with app.app_context():
            form = IssueForm(
                name=name,
                scope_id=scope_id,
                category_id=category_id,
                is_active=is_active,
                fields=fields if fields is not None else deepcopy(DEFAULT_FORM_FIELDS),
            )
            _db.session.add(form)
            _db.session.commit()
            return form.id
    return _make


@pytest.fixture
def make_user(app):
    def _make(email, role="user", password="Password1", approver_id=None,
              is_active=True, scope_ids=None, must_change_password=False):
        with app.app_context():
            user = User(
                email=email,
                display_name=email.split("@")[0],
                password_hash=generate_password_hash(password),
                role=role,
                approver_id=approver_id,
                is_active=is_active,
                must_change_password=must_change_password,
            )
            _db.session.add(user)
            _db.session.flush()
            for sid in (scope_ids or []):
                _db.session.add(UserScope(user_id=user.id, scope_id=sid))
            _db.session.commit()
            return user.id
    return _make


@pytest.fixture
def make_ticket(app):
    def _make(form_id, created_by, assigned_to=None, subject="Test ticket",
              scope="AR", status="Pending", payload=None):
        with app.app_context():
            ticket = Ticket(
                ticket_number=f"ACC-TEST-{os.urandom(4).hex()}",
                form_id=form_id,
                created_by=created_by,
                assigned_to=assigned_to,
                subject=subject,
                payload=payload or {},
                scope=scope,
                current_status=status,
            )
            _db.session.add(ticket)
            _db.session.commit()
            return ticket.id
    return _make


# ── Logged-in role fixtures ──────────────────────────────────────────────

def _login(client, email, password="Password1"):
    token = get_csrf_token(client, "/auth/login")
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        headers={"X-CSRFToken": token},
        follow_redirects=True,
    )


@pytest.fixture
def admin_user(make_user):
    return make_user("admin@test.com", role="admin")


@pytest.fixture
def approver_user(make_user):
    return make_user("approver@test.com", role="approver")


@pytest.fixture
def requester_user(make_user, approver_user):
    return make_user("requester@test.com", role="user", approver_id=approver_user)


@pytest.fixture
def admin_client(app, admin_user):
    c = app.test_client()
    _login(c, "admin@test.com")
    return c


@pytest.fixture
def approver_client(app, approver_user):
    c = app.test_client()
    _login(c, "approver@test.com")
    return c


@pytest.fixture
def requester_client(app, requester_user):
    c = app.test_client()
    _login(c, "requester@test.com")
    return c
