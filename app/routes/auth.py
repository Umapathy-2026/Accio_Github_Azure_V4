from datetime import datetime, timezone, timedelta
import hashlib
import secrets
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth',
                    template_folder='../templates/auth')


# ── Helpers ──────────────────────────────────────────────────────────────────

def role_required(*roles):
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_password_strength(password):
    errors = []
    if len(password) < 8:
        errors.append('Password must be at least 8 characters.')
    if not any(c.isupper() for c in password):
        errors.append('Password must contain at least one uppercase letter.')
    if not any(c.isdigit() for c in password):
        errors.append('Password must contain at least one number.')
    return errors


def redirect_to_dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif current_user.role == 'approver':
        return redirect(url_for('appr.queue'))
    return redirect(url_for('req.dashboard'))


def _build_msal_app():
    """Build a confidential MSAL client application."""
    import msal
    return msal.ConfidentialClientApplication(
        client_id=current_app.config['ENTRA_CLIENT_ID'],
        client_credential=current_app.config['ENTRA_CLIENT_SECRET'],
        authority=f"https://login.microsoftonline.com/"
                  f"{current_app.config['ENTRA_TENANT_ID']}"
    )


# ── Local Auth Routes ─────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_to_dashboard()

    # In Entra mode: GET requests redirect straight to Microsoft
    if current_app.config.get('AUTH_MODE') == 'entra':
        if request.method == 'GET':
            return redirect(url_for('auth.entra_login'))
        # POST should not happen in Entra mode — redirect anyway
        return redirect(url_for('auth.entra_login'))

    # Local mode: username/password form
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter your email and password.', 'error')
            return render_template('auth/login.html',
                                   auth_mode=current_app.config.get('AUTH_MODE', 'local'))

        user = User.query.filter_by(email=email).first()

        if user and user.locked_until and \
                user.locked_until > datetime.now(timezone.utc):
            remaining = (user.locked_until -
                         datetime.now(timezone.utc)).seconds // 60
            flash(
                f'Your account is locked. Try again in {remaining} minutes, '
                f'or contact your administrator.',
                'error'
            )
            return render_template('auth/login.html',
                                   auth_mode=current_app.config.get('AUTH_MODE', 'local'))

        if user and user.is_active and \
                user.password_hash and \
                check_password_hash(user.password_hash, password):
            user.failed_attempts = 0
            user.locked_until = None
            db.session.commit()
            login_user(user)
            if user.must_change_password:
                return redirect(url_for('auth.force_change_password'))
            return redirect_to_dashboard()

        # Failed attempt
        if user:
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= 3:
                user.locked_until = (datetime.now(timezone.utc)
                                     + timedelta(minutes=30))
                db.session.commit()
                flash('Too many failed attempts. Account locked for 30 minutes.', 'error')
                return render_template('auth/login.html',
                                       auth_mode=current_app.config.get('AUTH_MODE', 'local'))
            db.session.commit()

        flash('Invalid email or password.', 'error')

    return render_template('auth/login.html',
                           auth_mode=current_app.config.get('AUTH_MODE', 'local'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    # Entra mode: passwords are managed by Microsoft
    if current_app.config.get('AUTH_MODE') == 'entra':
        flash(
            'Password reset is managed by your organisation\'s Microsoft account. '
            'Please visit your Microsoft account portal to reset your password.',
            'info'
        )
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('auth/forgot_password.html')

        user = User.query.filter_by(email=email).first()
        if user and user.is_active:
            token = secrets.token_urlsafe(48)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            user.reset_token = token_hash
            user.reset_token_expiry = (datetime.now(timezone.utc)
                                       + timedelta(hours=1))
            db.session.commit()

            reset_url = url_for('auth.reset_password', token=token,
                                _external=True)
            from app.utils.email import send_password_reset
            send_password_reset(user.email, reset_url)

        flash(
            'If an account exists with that email, '
            'a password reset link has been sent.',
            'info'
        )
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = User.query.filter_by(reset_token=token_hash).first()

    if not user or not user.reset_token_expiry or \
            user.reset_token_expiry < datetime.now(timezone.utc):
        flash('This reset link is invalid or has expired.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        errors = validate_password_strength(new_password)
        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template('auth/reset_password.html', token=token)

        if new_password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token)

        user.password_hash = generate_password_hash(new_password)
        user.reset_token = None
        user.reset_token_expiry = None
        user.must_change_password = False
        db.session.commit()
        flash('Password reset successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def force_change_password():
    # Entra users never need to change a local password
    if current_user.entra_oid:
        return redirect_to_dashboard()

    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password     = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not check_password_hash(current_user.password_hash, current_password):
            flash('Current password is incorrect.', 'error')
            return render_template('auth/force_change_password.html')

        errors = validate_password_strength(new_password)
        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template('auth/force_change_password.html')

        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return render_template('auth/force_change_password.html')

        current_user.password_hash = generate_password_hash(new_password)
        current_user.must_change_password = False
        db.session.commit()
        flash('Password changed successfully.', 'success')
        return redirect_to_dashboard()

    return render_template('auth/force_change_password.html')


@auth_bp.route('/logout')
@login_required
def logout():
    # Entra mode: sign out from Microsoft too
    if current_app.config.get('AUTH_MODE') == 'entra' and \
            current_user.entra_oid:
        logout_user()
        session.clear()
        tenant_id = current_app.config['ENTRA_TENANT_ID']
        post_logout = url_for('auth.login', _external=True)
        return redirect(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout"
            f"?post_logout_redirect_uri={post_logout}"
        )
    logout_user()
    session.clear()
    return redirect(url_for('auth.login'))


# ── Microsoft Entra ID Routes (Model B — Just-in-Time Provisioning) ──────────

@auth_bp.route('/entra/login')
def entra_login():
    """Redirect user to Microsoft login page."""
    if not current_app.config.get('ENTRA_CLIENT_ID'):
        flash('Microsoft SSO is not configured. Please contact your administrator.', 'error')
        return redirect(url_for('auth.login'))

    state = secrets.token_urlsafe(16)
    session['entra_state'] = state

    cca = _build_msal_app()
    auth_url = cca.get_authorization_request_url(
        scopes=current_app.config['ENTRA_SCOPES'],
        redirect_uri=current_app.config['ENTRA_REDIRECT_URI'],
        state=state
    )
    return redirect(auth_url)


@auth_bp.route('/entra/callback')
def entra_callback():
    """
    Handle Microsoft's redirect after authentication.
    Implements Model B: Just-in-Time provisioning.
    - First login: auto-creates a basic profile from the Microsoft token
    - Subsequent logins: finds the existing profile by entra_oid
    - New users are flagged for admin setup (no role/approver/scope yet)
    """
    # Validate CSRF state
    expected_state = session.pop('entra_state', None)
    if not expected_state or request.args.get('state') != expected_state:
        flash('Authentication failed: invalid state. Please try again.', 'error')
        return redirect(url_for('auth.login'))

    # Check for errors returned by Microsoft
    error = request.args.get('error')
    if error:
        error_description = request.args.get('error_description', error)
        current_app.logger.error(f'Entra callback error: {error_description}')
        flash('Microsoft authentication failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))

    code = request.args.get('code')
    if not code:
        flash('Authentication failed: no code received. Please try again.', 'error')
        return redirect(url_for('auth.login'))

    # Exchange code for token
    cca = _build_msal_app()
    result = cca.acquire_token_by_authorization_code(
        code=code,
        scopes=current_app.config['ENTRA_SCOPES'],
        redirect_uri=current_app.config['ENTRA_REDIRECT_URI']
    )

    if 'error' in result:
        current_app.logger.error(f'MSAL token error: {result.get("error_description")}')
        flash('Microsoft authentication failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))

    # Extract identity claims from the token
    claims = result.get('id_token_claims', {})
    entra_oid   = claims.get('oid')
    email       = (claims.get('preferred_username') or
                   claims.get('email') or '').strip().lower()
    display_name = claims.get('name') or email.split('@')[0]

    if not entra_oid or not email:
        flash('Could not retrieve your identity from Microsoft. '
              'Please contact your administrator.', 'error')
        return redirect(url_for('auth.login'))

    # ── Model B: Just-in-Time Provisioning ───────────────────────────────────
    is_new_user = False

    # Look up by entra_oid first (most reliable), then fall back to email
    user = User.query.filter_by(entra_oid=entra_oid).first()

    if not user:
        # Try to link an existing manually-created profile by email
        user = User.query.filter_by(email=email).first()
        if user:
            # Link the existing profile to this Entra identity
            user.entra_oid = entra_oid
            db.session.commit()
        else:
            # First time this person has ever logged in — create their profile
            user = User(
                email=email,
                display_name=display_name,
                password_hash='',          # No local password for Entra users
                role='user',
                is_active=True,
                must_change_password=False,
                entra_oid=entra_oid
            )
            db.session.add(user)
            db.session.commit()
            is_new_user = True
            current_app.logger.info(
                f'JIT provisioned new user: {email} (entra_oid={entra_oid})'
            )

    if not user.is_active:
        flash('Your account has been deactivated. '
              'Please contact your administrator.', 'error')
        return redirect(url_for('auth.login'))

    login_user(user)

    # Inform newly provisioned users they need admin setup
    if is_new_user:
        flash(
            'Welcome to ACCIO. Your account has been created. '
            'Please contact your administrator to be assigned '
            'access before creating requests.',
            'info'
        )

    return redirect_to_dashboard()