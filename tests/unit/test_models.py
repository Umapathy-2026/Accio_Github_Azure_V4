import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Scope, Category, User, Ticket, IssueForm


def test_scope_name_unique(app, make_scope):
    make_scope(name="AR")
    with app.app_context():
        db.session.add(Scope(name="AR"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_category_unique_per_scope(app, make_scope, make_category):
    scope_id = make_scope(name="AR")
    make_category(scope_id, name="Billing")
    with app.app_context():
        db.session.add(Category(name="Billing", scope_id=scope_id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_category_same_name_different_scope_allowed(app, make_scope, make_category):
    ar_id = make_scope(name="AR")
    gl_id = make_scope(name="GL")
    make_category(ar_id, name="Billing")
    with app.app_context():
        db.session.add(Category(name="Billing", scope_id=gl_id))
        db.session.commit()  # should not raise
        assert Category.query.filter_by(name="Billing").count() == 2


def test_user_email_unique(app, make_user):
    make_user("dup@test.com")
    with app.app_context():
        from werkzeug.security import generate_password_hash
        db.session.add(User(
            email="dup@test.com",
            display_name="Dup",
            password_hash=generate_password_hash("Password1"),
            role="user",
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_ticket_number_unique(app, make_scope, make_form, make_user):
    scope_id = make_scope()
    form_id = make_form(scope_id)
    user_id = make_user("u@test.com")
    with app.app_context():
        t1 = Ticket(ticket_number="ACC-DUP", form_id=form_id, created_by=user_id,
                    subject="A", payload={}, scope="AR", current_status="Pending")
        db.session.add(t1)
        db.session.commit()

        t2 = Ticket(ticket_number="ACC-DUP", form_id=form_id, created_by=user_id,
                    subject="B", payload={}, scope="AR", current_status="Pending")
        db.session.add(t2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_ticket_relationships(app, make_scope, make_form, make_user, make_ticket):
    scope_id = make_scope()
    form_id = make_form(scope_id, name="Refund")
    approver_id = make_user("appr@test.com", role="approver")
    requester_id = make_user("req@test.com", role="user", approver_id=approver_id)
    ticket_id = make_ticket(form_id, created_by=requester_id, assigned_to=approver_id)

    with app.app_context():
        ticket = Ticket.query.get(ticket_id)
        assert ticket.creator.email == "req@test.com"
        assert ticket.assignee.email == "appr@test.com"
        assert ticket.issue_form.name == "Refund"


def test_user_scopes_relationship(app, make_scope, make_user):
    ar_id = make_scope(name="AR")
    gl_id = make_scope(name="GL")
    user_id = make_user("multi@test.com", scope_ids=[ar_id, gl_id])
    with app.app_context():
        user = User.query.get(user_id)
        names = sorted(s.name for s in user.scopes)
        assert names == ["AR", "GL"]
