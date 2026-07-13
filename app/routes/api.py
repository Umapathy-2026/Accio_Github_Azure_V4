from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import text

from app import db, csrf, limiter
from app.models import IssueForm, Notification

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/health')
@csrf.exempt
def health():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({
            'status': 'ok',
            'service': 'ACCIO',
            'db': 'connected',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        current_app.logger.error(f'Health check DB failure: {e}')
        return jsonify({
            'status': 'error',
            'db': 'unavailable'
        }), 503


@api_bp.route('/form-fields/<int:form_id>')
@login_required
def get_form_fields(form_id):
    form = IssueForm.query.get_or_404(form_id)

    if not form.is_active:
        return jsonify({'error': 'Form is not active'}), 404

    # Normalize options: handle both comma-separated strings (legacy) and arrays
    normalized_fields = []
    for field in form.fields:
        f = dict(field)
        if f.get('type') == 'dropdown' and isinstance(f.get('options'), str):
            f['options'] = [o.strip() for o in f['options'].split(',') if o.strip()]
        normalized_fields.append(f)

    return jsonify({
        'id': form.id,
        'name': form.name,
        'fields': normalized_fields
    })


@api_bp.route('/notifications')
@login_required
def get_notifications():
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    recent = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).limit(5).all()

    return jsonify({
        'unread_count': unread_count,
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat()
        } for n in recent]
    })


@api_bp.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_one_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first()
    if notif:
        notif.is_read = True
        db.session.commit()
    return jsonify({'success': True})