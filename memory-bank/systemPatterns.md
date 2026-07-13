Tech stack
- Python: 3.12 (runtime.txt)
- Flask: 3.0.3
- SQLAlchemy: Flask-SQLAlchemy 3.1.1
- Flask-Login: 0.6.3
- Flask-WTF (CSRF): 1.2.1
- Flask-Limiter (rate limiting): 3.5.0
- Werkzeug: 3.0.3
- openpyxl (Excel): 3.1.2
- gunicorn: 21.2.0 (production server)
- pyodbc (Azure SQL): 5.1.0
- azure-storage-blob: 12.19.0
- python-dotenv: 1.0.1

Architecture
- Application factory in app/__init__.py creates and configures the Flask app
  - Initializes SQLAlchemy, LoginManager, CSRFProtect, and Limiter
  - Registers blueprints: auth, requester (req), approver (appr), admin, api
  - Handles session security, rate limit errors, and password-change enforcement
- Blueprints (app/routes):
  - auth.py: login, logout, forgot/reset/force-change password; role decorator
  - requester.py: dashboard, new ticket, ticket detail, clarify, export to Excel, notifications
  - approver.py: queues (AR/GL), approve/reject/send back/reassign, bulk actions
  - admin.py: dashboard metrics, user and form management, exports, audit log
  - api.py: health check, dynamic form-fields, notifications APIs
- Utilities (app/utils):
  - email.py: SMTP email helpers and templated notifications
  - storage.py: file validation and Azure Blob/local storage handling

Folder structure (annotated)
- app/
  - __init__.py — factory, config, blueprint registration, seeding (dev-only)
  - models.py — ORM models: User, IssueForm, Ticket, ApprovalLog, Notification, AdminAuditLog
  - routes/
    - auth.py — authentication and password flows
    - requester.py — ticket creation and viewing; Excel export with sanitize_cell()
    - approver.py — approval actions and queues
    - admin.py — admin UX, exports, and audit log
    - api.py — JSON endpoints for health, forms, notifications
  - utils/
    - email.py — SMTP send and notification templates
    - storage.py — file validation and Azure Blob/local save, SAS URLs
  - templates/ — Jinja2 templates (admin, approver, auth, requester, base)
  - static/ — static assets
- wsgi.py — entrypoint for gunicorn
- requirements.txt — pinned dependencies
- gunicorn.conf.py / Procfile / startup.sh — deployment runtime config

Design patterns and practices
- Factory pattern for app creation (create_app)
- Blueprint modularization for features
- ORM with SQLAlchemy models; relationships and indexes defined
- Defensive defaults for session cookies and rate limiting
- Email sending isolated behind utility function
- Excel generation encapsulated in routes with sanitize_cell() for security

Database
- ORM: SQLAlchemy via Flask-SQLAlchemy
- Engines: SQLite (default for local dev instance/instance/ticketing.db) or Azure SQL via SQLALCHEMY_DATABASE_URI (pyodbc)
- Pooling tuned when using mssql/pyodbc (pre_ping, recycle, pool_size)
- Migrations: none detected; tables created on startup via db.create_all()