Environment variables
- SECRET_KEY — Required. Strong random string for session signing. Example: generated via Python secrets.
- FLASK_ENV — Environment name. Example: development or production. Controls dev-only seeding.
- FLASK_DEBUG — Flask debug mode flag. Example: false in production.
- SQLALCHEMY_DATABASE_URI — Database URI; Azure SQL via pyodbc or omit for local SQLite. Example: mssql+pyodbc://...driver=ODBC+Driver+18+for+SQL+Server
- MAIL_USERNAME — SMTP login (Office365).
- MAIL_PASSWORD — SMTP password/app password.
- AZURE_STORAGE_CONNECTION_STRING — Azure Blob Storage connection string.
- AZURE_STORAGE_CONTAINER — Blob container name. Default: accio-uploads.
- TEST_ADMIN_PASSWORD — Only used by check.py test script to login as admin in test runs.

External services/APIs
- Azure SQL Database (via pyodbc when configured)
- Azure Blob Storage for attachments in production
- Office365 SMTP for sending transactional emails to users/approvers

Authentication method
- Email/password using Werkzeug password hashes stored on User.password_hash
- Lockout after 5 failed attempts for 30 minutes; must_change_password enforced on first login where applicable

Session and CSRF setup
- SECRET_KEY required; session cookies secure/httponly with SameSite=Lax (secure only in production)
- CSRF via Flask-WTF enabled globally; selective @csrf.exempt for API health

Rate limiting setup
- Flask-Limiter default limits: 500/day and 100/hour per IP using in-memory storage
- Custom handler returns 429 JSON for API routes and flashes warning for web views

Excel/file generation libraries
- openpyxl for Excel export; sanitize_cell() prevents formula injection
- python-magic used opportunistically for MIME sniffing on uploads; falls back to extension check

Deployment target
- Local development with SQLite (instance folder) and flask/gunicorn
- Azure App Service (Linux): gunicorn with configuration in Procfile/gunicorn.conf.py and startup.sh installing system deps