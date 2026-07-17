import os
import warnings
from flask import Flask, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
csrf = CSRFProtect()
limiter = Limiter(get_remote_address, default_limits=["500 per day", "100 per hour"], storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"))


def create_app(testing=False):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    instance_dir = os.path.join(os.path.dirname(base_dir), 'instance')
    os.makedirs(instance_dir, exist_ok=True)

    app = Flask(__name__, static_folder='static', instance_path=instance_dir)

    # SECRET_KEY validation
    # For security, we do not allow a fallback SECRET_KEY in any environment.
    # A strong, random SECRET_KEY must be provided via environment variable.
    secret = os.getenv('SECRET_KEY')
    if not secret:
        raise RuntimeError("FATAL: SECRET_KEY environment variable is not set. Set SECRET_KEY to a strong random value.")
    app.config['SECRET_KEY'] = secret

    # Session cookie security
    is_production = os.getenv('FLASK_ENV') == 'production'
    app.config['SESSION_COOKIE_SECURE'] = is_production
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'None' if is_production else 'Lax'
    app.config['REMEMBER_COOKIE_SECURE'] = is_production
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True

    # Database — env var takes priority, SQLite fallback for local dev only
    default_db = 'sqlite:///' + os.path.join(instance_dir, 'ticketing.db')
    db_uri = os.getenv('SQLALCHEMY_DATABASE_URI') or default_db
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Azure SQL pool settings (only if using mssql)
    _using_azure_sql = 'mssql' in db_uri or 'pyodbc' in db_uri
    if _using_azure_sql:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 1800,
            'pool_size': 5,
            'max_overflow': 10,
            'connect_args': {'timeout': 30}
        }

    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
    app.config['UPLOAD_FOLDER'] = os.path.join(instance_dir, 'uploads')
    app.config['MAIL_SERVER'] = 'smtp.office365.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', '')
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['AZURE_STORAGE_ACCOUNT_URL'] = os.getenv('AZURE_STORAGE_ACCOUNT_URL', '')
    app.config['AZURE_STORAGE_CONTAINER'] = os.getenv('AZURE_STORAGE_CONTAINER', 'accio-uploads')

    # Authentication mode: 'local' (username/password) or 'entra' (Microsoft SSO)
    app.config['AUTH_MODE']           = os.getenv('AUTH_MODE', 'local')
    app.config['ENTRA_CLIENT_ID']     = os.getenv('ENTRA_CLIENT_ID', '')
    app.config['ENTRA_CLIENT_SECRET'] = os.getenv('ENTRA_CLIENT_SECRET', '')
    app.config['ENTRA_TENANT_ID']     = os.getenv('ENTRA_TENANT_ID', '')
    app.config['ENTRA_REDIRECT_URI']  = os.getenv('ENTRA_REDIRECT_URI', '')
    app.config['ENTRA_SCOPES']        = ['User.Read']

    # Email: set MAIL_DEV_MODE=true to log emails to App Service log stream
    # instead of sending them — useful when SMTP is not yet configured
    app.config['MAIL_DEV_MODE'] = os.getenv('MAIL_DEV_MODE', 'false').lower() == 'true'

    # Override MAIL_SERVER/PORT from environment if provided
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', app.config['MAIL_SERVER'])
    app.config['MAIL_PORT']   = int(os.getenv('MAIL_PORT', str(app.config['MAIL_PORT'])))

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        user = User.query.get(int(user_id))
        if user is None:
            return None
        if not user.is_active:
            return None
        return user

    # Force password change guard
    @app.before_request
    def enforce_password_change():
        from flask_login import current_user
        allowed_endpoints = {'auth.force_change_password', 'auth.logout', 'static'}
        if (current_user.is_authenticated
                and current_user.must_change_password
                and request.endpoint not in allowed_endpoints):
            return redirect(url_for('auth.force_change_password'))

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if is_production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # Rate limit exceeded handler
    from flask_limiter.errors import RateLimitExceeded

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(e):
        if request.is_json or request.path.startswith('/api'):
            return jsonify(error="Too many requests. Please try again later."), 429
        flash("Too many requests. Please wait a moment and try again.", "warning")
        referrer = request.referrer or ''
        parsed = urlparse(referrer)
        safe_back = referrer if (not parsed.netloc or parsed.netloc == request.host) else ''
        return redirect(safe_back or url_for('auth.login'))

    from app.routes.auth import auth_bp
    from app.routes.requester import req_bp
    from app.routes.approver import appr_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(req_bp)
    app.register_blueprint(appr_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        from app.models import User, IssueForm, Ticket, ApprovalLog, Notification, AdminAuditLog

        # Run pending Alembic migrations so the schema always matches models.py.
        # This is equivalent to `flask db upgrade` and runs all pending revisions
        # in order. On a fresh database this creates all tables; on an existing
        # database it applies any migrations that haven't run yet.
        # If the database is unreachable, let the error propagate
        # so Azure App Service reports a clear startup failure rather than silently
        # routing data to SQLite. A visible crash is safer than undetected data loss.
        from flask_migrate import upgrade
        upgrade()
        if _using_azure_sql:
            app.logger.info("Connected to Azure SQL successfully.")

        # Seed only in explicit development environments to avoid accidental prod/admin creds
        try:
            if os.getenv('FLASK_ENV') == 'development':
                seed_database()
        except Exception as e:
            app.logger.error("Seed database failed (non-fatal): %s", e)

    return app


def seed_database():
    from app.models import User, Scope

    # Create scopes idempotently
    for scope_name in ('AR', 'GL'):
        existing = Scope.query.filter_by(name=scope_name).first()
        if not existing:
            db.session.add(Scope(name=scope_name, is_active=True))
    db.session.commit()

    # Create default admin user idempotently
    if User.query.filter_by(email='admin@company.com').first() is None:
        from werkzeug.security import generate_password_hash
        import secrets
        _generated_admin_pwd = secrets.token_urlsafe(16)
        admin = User(
            email='admin@company.com',
            display_name='Admin',
            password_hash=generate_password_hash(_generated_admin_pwd),
            role='admin',
            is_active=True,
            must_change_password=True
        )
        db.session.add(admin)
        db.session.commit()
        print(f"[SETUP] Seeded default admin user. Email: admin@company.com, Temporary Password: {_generated_admin_pwd}")
    else:
        print("[SETUP] Admin user already exists, skipping seed.")
