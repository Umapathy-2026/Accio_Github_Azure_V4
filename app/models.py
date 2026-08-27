import enum
from datetime import datetime, timezone
from flask_login import UserMixin
from app import db


def utcnow():
    return datetime.now(timezone.utc)


def aware_utc(dt):
    """SQLite (and SQL Server DATETIME) drop tzinfo on write, so values read
    back from the DB are naive even though they were stored as UTC. Attach
    UTC tzinfo before comparing against a tz-aware datetime.now(timezone.utc)
    to avoid 'can't compare offset-naive and offset-aware datetimes'."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class UserRole(str, enum.Enum):
    USER = 'user'
    APPROVER = 'approver'
    ADMIN = 'admin'


class TicketStatus(str, enum.Enum):
    PENDING = 'Pending'
    UNDER_REVIEW = 'Under Review'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'
    NEEDS_CLARIFICATION = 'Needs Clarification'
    SENT_TO_FULFILMENT = 'Sent to Fulfilment'


class ApprovalAction(str, enum.Enum):
    SUBMITTED = 'Submitted'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'
    SENT_BACK = 'Sent Back'
    CLARIFICATION_PROVIDED = 'Clarification Provided'
    REASSIGNED = 'Reassigned'
    SENT_TO_FULFILMENT = 'Sent to Fulfilment'


class Scope(db.Model):
    __tablename__ = 'scopes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f'<Scope {self.name}>'


class UserScope(db.Model):
    __tablename__ = 'user_scopes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    scope_id = db.Column(db.Integer, db.ForeignKey('scopes.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'scope_id', name='uq_user_scope'),
    )


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    scope_id = db.Column(db.Integer, db.ForeignKey('scopes.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    scope_obj = db.relationship('Scope')

    __table_args__ = (
        db.UniqueConstraint('name', 'scope_id', name='uq_category_scope'),
    )

    def __repr__(self):
        return f'<Category {self.name}>'


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False, server_default='')
    role = db.Column(db.String(20), nullable=False, default='user')
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    reset_token = db.Column(db.String(128), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    entra_oid = db.Column(db.String(36), unique=True, nullable=True, index=True)

    approver = db.relationship('User', remote_side=[id], backref='subordinates')
    scopes = db.relationship('Scope', secondary='user_scopes', lazy='dynamic')

    def get_id(self):
        return str(self.id)

    @property
    def is_locked(self):
        locked_until = aware_utc(self.locked_until)
        return bool(locked_until and locked_until > utcnow())

    def __repr__(self):
        return f'<User {self.email}>'


class IssueForm(db.Model):
    __tablename__ = 'issue_forms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(500), nullable=False)
    scope_id = db.Column(db.Integer, db.ForeignKey('scopes.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    fields = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, default=utcnow)

    scope_obj = db.relationship('Scope')
    category_obj = db.relationship('Category')
    tickets = db.relationship('Ticket', backref='issue_form', lazy='dynamic')

    def __repr__(self):
        return f'<IssueForm {self.name}>'


class Ticket(db.Model):
    __tablename__ = 'tickets'
    __table_args__ = (
        db.Index('idx_ticket_assigned_status', 'assigned_to', 'current_status'),
        db.Index('idx_ticket_created_status', 'created_by', 'current_status'),
        db.Index('idx_ticket_created_at', 'created_at'),
        db.Index('idx_ticket_form', 'form_id'),
        db.UniqueConstraint('ticket_number', name='uq_ticket_number'),
    )

    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    form_id = db.Column(db.Integer, db.ForeignKey('issue_forms.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    subject = db.Column(db.String(500), nullable=False, default='')
    description = db.Column(db.Text, nullable=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    attachment_name = db.Column(db.String(255), nullable=True)
    attachment_path = db.Column(db.String(500), nullable=True)
    scope = db.Column(db.String(50), nullable=False, default='')
    current_status = db.Column(db.String(30), nullable=False, default='Pending')
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    creator = db.relationship('User', foreign_keys=[created_by], backref='created_tickets')
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_tickets')
    approval_logs = db.relationship('ApprovalLog', backref='ticket', lazy='dynamic', order_by='ApprovalLog.timestamp')

    def __repr__(self):
        return f'<Ticket {self.ticket_number}>'


class ApprovalLog(db.Model):
    __tablename__ = 'approval_logs'
    __table_args__ = (
        db.Index('idx_log_ticket', 'ticket_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    action_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=utcnow)

    actor = db.relationship('User', foreign_keys=[action_by])

    def __repr__(self):
        return f'<ApprovalLog {self.action} on Ticket {self.ticket_id}>'


class Notification(db.Model):
    __tablename__ = 'notifications'
    __table_args__ = (
        db.Index('idx_notif_user_read', 'user_id', 'is_read'),
        db.Index('idx_notif_created', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship('User', backref='notifications')

    def __repr__(self):
        return f'<Notification {self.title}>'


class AdminAuditLog(db.Model):
    __tablename__ = 'admin_audit_log'
    __table_args__ = (
        db.Index('idx_audit_actor', 'performed_by'),
        db.Index('idx_audit_timestamp', 'timestamp'),
    )

    id = db.Column(db.Integer, primary_key=True)
    performed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50))
    target_id = db.Column(db.Integer)
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=utcnow)

    actor = db.relationship('User', foreign_keys=[performed_by])


DEFAULT_FORM_FIELDS = [
    {"id": "subject",     "label": "Subject",     "type": "text",     "required": True,  "protected": True},
    {"id": "description", "label": "Description", "type": "textarea", "required": False, "protected": True},
    {"id": "attachments", "label": "Attachments", "type": "file",     "required": False, "protected": True},
]