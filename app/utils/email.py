import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from markupsafe import escape


def send_email(to_email, subject, body_html):
    """
    Send an HTML email via Office365 SMTP.
    In production, this will connect to Azure Communication Services or similar.
    """
    app = current_app._get_current_object()

    # Dev mode: log email to stdout instead of sending
    # Enable by setting MAIL_DEV_MODE=true in App Service environment variables
    if app.config.get('MAIL_DEV_MODE'):
        app.logger.info(
            f"\n{'='*60}\n"
            f"[DEV EMAIL — NOT SENT]\n"
            f"To:      {to_email}\n"
            f"Subject: {subject}\n"
            f"{'='*60}"
        )
        return True

    username = app.config.get('MAIL_USERNAME')
    password = app.config.get('MAIL_PASSWORD')

    if not username or not password:
        app.logger.warning('Mail credentials not configured. Skipping email send.')
        return False

    msg = MIMEMultipart('alternative')
    msg['From'] = username
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body_html, 'html'))

    try:
        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(username, [to_email], msg.as_string())
        return True
    except Exception as e:
        app.logger.error(f'Failed to send email to {to_email}: {str(e)}')
        return False


def send_ticket_created(ticket, approver_email, review_url):
    safe_subject = escape(ticket.subject)
    safe_ticket_num = escape(ticket.ticket_number)
    safe_creator = escape(ticket.creator.display_name)
    safe_form = escape(ticket.issue_form.name)
    subject = f'[ACCIO] New Ticket: {ticket.ticket_number} - {ticket.subject}'
    body_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
        <div style="border-bottom: 2px solid #01696f; padding-bottom: 12px; margin-bottom: 24px;">
            <h1 style="color: #01696f; font-size: 24px; margin: 0;">ACCIO</h1>
            <p style="color: #6b6a68; font-size: 14px; margin: 4px 0 0;">ACCIO Finance Approval System</p>
        </div>
        <h2 style="color: #1a1917; font-size: 18px;">New Ticket Requires Your Approval</h2>
        <p style="color: #6b6a68; font-size: 14px;">Ticket <strong>{safe_ticket_num}</strong> has been submitted by <strong>{safe_creator}</strong> and requires your review.</p>
        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
            <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #6b6a68; font-size: 13px;">Issue Type</td><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #1a1917; font-size: 13px; font-weight: 600;">{safe_form}</td></tr>
            <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #6b6a68; font-size: 13px;">Subject</td><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #1a1917; font-size: 13px; font-weight: 600;">{safe_subject}</td></tr>
            <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #6b6a68; font-size: 13px;">Submitted By</td><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #1a1917; font-size: 13px; font-weight: 600;">{safe_creator}</td></tr>
        </table>
        <p style="margin: 24px 0 0;">
            <a href="{review_url}" style="display: inline-block; background: #01696f; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-size: 14px; font-weight: 600;">Review Ticket</a>
        </p>
        <p style="color: #b0afa9; font-size: 12px; margin-top: 32px; border-top: 1px solid #e0e0e0; padding-top: 16px;">This is an automated message from ACCIO. Please do not reply directly to this email.</p>
    </div>
    """
    send_email(approver_email, subject, body_html)


def send_ticket_approved(ticket, review_url):
    safe_subject = escape(ticket.subject)
    safe_ticket_num = escape(ticket.ticket_number)
    safe_approver = escape(ticket.assignee.display_name)
    subject = f'[ACCIO] Ticket Approved: {ticket.ticket_number}'
    body_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
        <div style="border-bottom: 2px solid #01696f; padding-bottom: 12px; margin-bottom: 24px;">
            <h1 style="color: #01696f; font-size: 24px; margin: 0;">ACCIO</h1>
            <p style="color: #6b6a68; font-size: 14px; margin: 4px 0 0;">ACCIO Finance Approval System</p>
        </div>
        <h2 style="color: #1a1917; font-size: 18px;">✅ Ticket Approved</h2>
        <p style="color: #6b6a68; font-size: 14px;">Your ticket <strong>{safe_ticket_num}</strong> has been approved and sent to fulfilment.</p>
        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
            <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #6b6a68; font-size: 13px;">Subject</td><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #1a1917; font-size: 13px; font-weight: 600;">{safe_subject}</td></tr>
            <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #6b6a68; font-size: 13px;">Approved By</td><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #1a1917; font-size: 13px; font-weight: 600;">{safe_approver}</td></tr>
        </table>
        <p style="margin: 24px 0 0;">
            <a href="{review_url}" style="display: inline-block; background: #01696f; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-size: 14px; font-weight: 600;">View Ticket</a>
        </p>
        <p style="color: #b0afa9; font-size: 12px; margin-top: 32px; border-top: 1px solid #e0e0e0; padding-top: 16px;">This is an automated message from ACCIO.</p>
    </div>
    """
    send_email(ticket.creator.email, subject, body_html)


def send_ticket_rejected(ticket, reason, review_url):
    safe_subject = escape(ticket.subject)
    safe_ticket_num = escape(ticket.ticket_number)
    safe_reason = escape(reason)
    safe_approver = escape(ticket.assignee.display_name)
    subject = f'[ACCIO] Ticket Rejected: {ticket.ticket_number}'
    body_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
        <div style="border-bottom: 2px solid #01696f; padding-bottom: 12px; margin-bottom: 24px;">
            <h1 style="color: #01696f; font-size: 24px; margin: 0;">ACCIO</h1>
            <p style="color: #6b6a68; font-size: 14px; margin: 4px 0 0;">ACCIO Finance Approval System</p>
        </div>
        <h2 style="color: #1a1917; font-size: 18px;">❌ Ticket Rejected</h2>
        <p style="color: #6b6a68; font-size: 14px;">Your ticket <strong>{safe_ticket_num}</strong> has been rejected.</p>
        <div style="background: #fef3f3; border-radius: 8px; padding: 16px; margin: 16px 0;">
            <p style="color: #991b1b; font-size: 13px; font-weight: 600; margin: 0 0 4px;">Reason for rejection:</p>
            <p style="color: #1a1917; font-size: 14px; margin: 0;">{safe_reason}</p>
        </div>
        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
            <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #6b6a68; font-size: 13px;">Subject</td><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #1a1917; font-size: 13px; font-weight: 600;">{safe_subject}</td></tr>
            <tr><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #6b6a68; font-size: 13px;">Rejected By</td><td style="padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #1a1917; font-size: 13px; font-weight: 600;">{safe_approver}</td></tr>
        </table>
        <p style="margin: 24px 0 0;">
            <a href="{review_url}" style="display: inline-block; background: #01696f; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-size: 14px; font-weight: 600;">View Ticket</a>
        </p>
        <p style="color: #b0afa9; font-size: 12px; margin-top: 32px; border-top: 1px solid #e0e0e0; padding-top: 16px;">This is an automated message from ACCIO.</p>
    </div>
    """
    send_email(ticket.creator.email, subject, body_html)


def send_ticket_sent_back(ticket, reason, review_url):
    safe_subject = escape(ticket.subject)
    safe_ticket_num = escape(ticket.ticket_number)
    safe_reason = escape(reason)
    subject = f'[ACCIO] Ticket Needs Clarification: {ticket.ticket_number}'
    body_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
        <div style="border-bottom: 2px solid #01696f; padding-bottom: 12px; margin-bottom: 24px;">
            <h1 style="color: #01696f; font-size: 24px; margin: 0;">ACCIO</h1>
            <p style="color: #6b6a68; font-size: 14px; margin: 4px 0 0;">ACCIO Finance Approval System</p>
        </div>
        <h2 style="color: #1a1917; font-size: 18px;">🔄 Clarification Required</h2>
        <p style="color: #6b6a68; font-size: 14px;">Your ticket <strong>{safe_ticket_num}</strong> needs additional information before it can be processed.</p>
        <div style="background: #fff8f0; border-radius: 8px; padding: 16px; margin: 16px 0;">
            <p style="color: #9a3412; font-size: 13px; font-weight: 600; margin: 0 0 4px;">What's needed:</p>
            <p style="color: #1a1917; font-size: 14px; margin: 0;">{safe_reason}</p>
        </div>
        <p style="margin: 24px 0 0;">
            <a href="{review_url}" style="display: inline-block; background: #01696f; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-size: 14px; font-weight: 600;">Review Ticket</a>
        </p>
        <p style="color: #b0afa9; font-size: 12px; margin-top: 32px; border-top: 1px solid #e0e0e0; padding-top: 16px;">This is an automated message from ACCIO.</p>
    </div>
    """
    send_email(ticket.creator.email, subject, body_html)


def send_clarification_provided(ticket, approver_email, review_url):
    safe_subject = escape(ticket.subject)
    safe_ticket_num = escape(ticket.ticket_number)
    safe_creator = escape(ticket.creator.display_name)
    subject = f'[ACCIO] Clarification Provided: {ticket.ticket_number}'
    body_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
        <div style="border-bottom: 2px solid #01696f; padding-bottom: 12px; margin-bottom: 24px;">
            <h1 style="color: #01696f; font-size: 24px; margin: 0;">ACCIO</h1>
            <p style="color: #6b6a68; font-size: 14px; margin: 4px 0 0;">ACCIO Finance Approval System</p>
        </div>
        <h2 style="color: #1a1917; font-size: 18px;">💬 Clarification Received</h2>
        <p style="color: #6b6a68; font-size: 14px;">The ticket <strong>{safe_ticket_num}</strong> has been updated with clarification by <strong>{safe_creator}</strong> and is ready for your review.</p>
        <p style="margin: 24px 0 0;">
            <a href="{review_url}" style="display: inline-block; background: #01696f; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-size: 14px; font-weight: 600;">Review Ticket</a>
        </p>
        <p style="color: #b0afa9; font-size: 12px; margin-top: 32px; border-top: 1px solid #e0e0e0; padding-top: 16px;">This is an automated message from ACCIO.</p>
    </div>
    """
    send_email(approver_email, subject, body_html)


def send_password_reset(to_email, reset_url):
    """Send a password reset email."""
    from markupsafe import escape
    safe_url = escape(reset_url)
    subject = '[ACCIO] Password Reset Request'
    body_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
        <div style="border-bottom: 2px solid #01696f; padding-bottom: 12px; margin-bottom: 24px;">
            <h1 style="color: #01696f; font-size: 24px; margin: 0;">ACCIO</h1>
            <p style="color: #6b6a68; font-size: 14px; margin: 4px 0 0;">ACCIO Finance Approval System</p>
        </div>
        <h2 style="color: #1a1917; font-size: 18px;">Password Reset Request</h2>
        <p style="color: #6b6a68; font-size: 14px;">
            We received a request to reset your ACCIO password.
            Click the button below to reset it. This link expires in 1 hour.
        </p>
        <p style="margin: 24px 0;">
            <a href="{safe_url}"
               style="display:inline-block;background:#01696f;color:white;
                      text-decoration:none;padding:12px 32px;border-radius:8px;
                      font-size:14px;font-weight:600;">
               Reset Password
            </a>
        </p>
        <p style="color: #6b6a68; font-size: 13px;">
            If you did not request this, you can safely ignore this email.
            Your password will not be changed.
        </p>
        <p style="color: #b0afa9; font-size: 12px; margin-top: 32px;
                  border-top: 1px solid #e0e0e0; padding-top: 16px;">
            This is an automated message from ACCIO. Please do not reply.
        </p>
    </div>
    """
    send_email(to_email, subject, body_html)