Current state after 2026-07-03 admin panel rebuild (Flask-Migrate + new schema)

Major changes:
- Flask-Migrate 4.0.7 added to requirements.txt and initialized in app/__init__.py
- New tables: scopes, user_scopes, categories
- User model: manager_id → approver_id, scope column removed, scopes relationship via UserScope junction
- IssueForm model: scope String(10) → scope_id FK to scopes.id, added category_id FK, is_deleted column, created_at
- Ticket model: scope String(10) → String(50) (still stores scope NAME at creation time)
- seed_database() now creates Scope rows (AR, GL) and admin user only — no IssueForm seeding
- Hardcoded scope validation ('AR'/'GL'/'') removed from admin.py routes
- requester.py updated: current_user.manager_id → current_user.approver_id, scope lookup via scope_obj.name
- Templates updated: user.scope → user.scopes.all(), form.scope → form.scope_obj.name, form_scope values now integer IDs
- Migration created: migrations/versions/0001_initial_schema.py with full schema
- Startup now runs `flask db upgrade` programmatically on every boot, ensuring schema is always current before queries run

Other notable context
- Tech stack and dependency versions pinned in requirements.txt (Flask 3.1.3, Flask-Migrate 4.0.7, etc.).
- App follows the factory pattern; blueprints for auth, requester, approver, admin, api are registered in create_app.
- Database auto-creates tables on startup if no alembic revision exists, then stamps the head. SQLite used by default via instance folder unless SQLALCHEMY_DATABASE_URI provided (supports Azure SQL via pyodbc).
- Email and file storage utilities encapsulated in app/utils; Azure Blob integration optional via env vars.
- Local development now expects a .env file. wsgi.py loads environment variables via python-dotenv (load_dotenv()), so set SECRET_KEY and FLASK_ENV in .env for local runs.

Known issues / TODOs
- Rate limiter uses in-memory storage, which may not be suitable for multi-instance production.
- Email sending may fail in low-permission environments; already wrapped in try/except with logging in requester routes.
- 2026-07-06: Three targeted fixes applied (new_ticket.html scope attr, api.py current_app import, admin.py duplicate export removal)
- 2026-07-07: Cosmetic sidebar fix in base.html — Admin "Request History" nav item moved below the divider, after "My Requests" (was previously between "All Tickets" and "Audit Log"). No functional/route changes.
- 2026-07-07: Login page UI overhaul — glassmorphic redesign of auth/login.html
  - Split-screen layout: LEFT half = large logo panel with glassmorphic background (rgba + backdrop-filter blur(20px)); RIGHT half = floating glassmorphic login credentials card
  - LEFT logo panel: 320px 3D elevated logo with perspective wrapper, layered drop-shadows (depth + brand glow), continuous rotateY/rotateX wobble (5s), pulsing radial glow behind logo, continuous shine sweep (diagonal gradient highlight, infinite 3.5s loop), brand text "ACCIO" below logo
  - RIGHT form panel: floating glassmorphic card (rgba(255,255,255,0.06) + backdrop-filter blur(24px) saturate(180%), 1px translucent border, inset highlight, gentle float animation)
  - Animated gradient background: 3 radial-gradient layers (brand teal/cyan) shifting on 18s loop + 3 floating blurred orbs for depth
  - Mouse-following particles (Antigravity-style): full-screen <canvas>, vanilla JS spawns glowing teal/cyan particles at cursor on mousemove/touchmove, particles fade+shrink with slight gravity, max 130 particles, requestAnimationFrame loop
  - Glass-themed form inputs, gradient submit button, glass Microsoft SSO button (Entra mode preserved)
  - All Flask/Jinja logic preserved: CSRF token, auth_mode conditional (entra vs local), form actions, forgot-password link
  - Accessibility: prefers-reduced-motion media query disables all animations
  - Responsive: panels stack vertically on < 768px; reduced padding/logo size on < 480px
  - No backend changes; inline <style>/<script> acceptable until CSP Phase 3 (future: move JS to external file with nonce)
- 2026-07-07: App-wide glassmorphic dark theme — base.html overhauled
  - CSS variables switched from light to dark glassmorphic: --bg #0e1830, --surface rgba(255,255,255,0.06), --text #ffffff, --primary #14b8a6
  - Animated gradient background (.app-bg) + 3 floating blurred orbs (.app-orb) added to all pages
  - Particle canvas (#particle-canvas) with mouse-following JS added to all pages (max 100 particles, lighter than login page's 130)
  - Header: glassmorphic (rgba bg + backdrop-filter blur(20px))
  - Sidebar: glassmorphic (rgba bg + backdrop-filter blur(20px))
  - Cards: glassmorphic (rgba bg + backdrop-filter blur(16px))
  - Tables: dark translucent headers, translucent row hover
  - Inputs: dark translucent bg, white text, teal focus glow
  - Buttons: gradient primary (teal→cyan), glass secondary
  - Modals: glassmorphic (surface-solid + backdrop-filter blur(24px))
  - Toasts: glassmorphic dark
  - Notifications panel: glassmorphic dark
  - Filter bar, pagination, bulk bar: all glassmorphic dark
  - Badges: translucent dark variants (yellow/blue/green/red/orange)
  - Tom Select: dark theme CSS overrides added
  - All text colors switched to white/light variants for dark background
  - All Flask/Jinja logic, JS functions (toast, session, notifications, modal, file select, spinner, copy, unsaved changes) preserved unchanged
- 2026-07-06: azure-pipelines.yml created with Build + Deploy stages and GitHub mirror step
- 2026-07-06: Microsoft Entra ID (Model B JIT provisioning) + email dev mode + branding fixes
  - requirements.txt: msal==1.37.0 added (updated from 1.28.0)
  - models.py: User.entra_oid column (String(36), unique, indexed); password_hash now server_default='' for Entra-only users
  - migration 0003_add_entra_oid_to_users.py created (revises 0002); unique=True removed from add_column (enforced via create_index only — correct for batch mode)
  - __init__.py: AUTH_MODE, ENTRA_CLIENT_ID/SECRET/TENANT_ID/REDIRECT_URI/SCOPES, MAIL_DEV_MODE, MAIL_SERVER/PORT env overrides
  - email.py: MAIL_DEV_MODE logs [DEV EMAIL — NOT SENT] instead of sending; all 5 "Finance AR Ticketing System" → "ACCIO Finance Approval System"; send_password_reset() added
  - auth.py: full Entra ID implementation (entra_login, entra_callback with JIT provisioning, entra-aware logout/forgot-password/force-change-password); local login now passes auth_mode to template
  - login.html: {% if auth_mode == 'entra' %} shows Microsoft SSO button, {% else %} shows local form
  - users.html: "Needs Setup" badge for users with no approver/scope; "Create User" → "Add User Manually" (button, modal title, submit button); warning about Microsoft SSO auto-provisioning
- 2026-07-03: Completed admin panel rebuild features
  - Scope management: list/create/toggle with protection against deactivation when active forms exist
  - Category management: list grouped by scope, create (name + scope), toggle with same protection
  - Form management: create uses active scopes dropdown (no "All"), optional category constrained to the chosen scope; default fields populated from DEFAULT_FORM_FIELDS; forms list shows scope/category and includes Delete (soft delete: is_deleted=True, is_active=False); edit view locks Subject/Description/Attachments, allows adding custom fields at index 1 and drag-reordering within the custom zone
  - User management: creation/edit now use multi-select checkboxes for scope access (UserScope rows created/updated); manager_id fully renamed to approver_id across UI; labels show "Assigned Approver"
  - Deactivate approver flow: deactivate-check returns subordinates_count and list; modal enforces selecting a new approver for subordinates; backend reassigns users and then applies ticket reassignment before deactivation; response flag renamed to has_dependencies
- Migration 0002 handles legacy Azure SQL databases: renames manager_id→approver_id, creates scopes/user_scopes/categories, converts issue_forms.scope to FK, drops users.scope
- seed_database() wrapped in try/except to prevent gunicorn crash on schema mismatch

---

2026-07-03 — Deployment verification status (Azure App Service)
- Code state: app/__init__.py contains programmatic Alembic `upgrade()`; migration `migrations/versions/0002_add_approver_id_to_users.py` is present. Both were introduced in commit c237afae (Fixes2).
- CI/CD configuration: `.github/workflows/fixes2_accio-demo.yml` deploys to Azure Web App `accio-demo` on pushes to branch `Fixes2` using `azure/webapps-deploy@v3`. No packaging filters exclude `migrations/`.
- Ignore/config review: `.gitignore` does not exclude `migrations/`. No `.deployment` or `.funcignore` files in repo. No Oryx exclusion rules detected.
- Deployment history: A clean redeploy was triggered with no-op commit 7e9998f on `Fixes2`. GitHub Actions workflow run #10 completed successfully with `head_sha=7e9998f` (2026-07-03T06:29Z → 06:31Z).
- Current gap: Awaiting Azure App Service Log stream from `accio-demo` to confirm startup runs Alembic upgrade and shows migration `0001 -> 0002` (rather than `stamp_revision -> 0001`).
- Next actions: Review the pasted startup log. If it still shows `stamp_revision`, verify the App Service is indeed deploying from GitHub Actions (Fixes2) and not from a different Deployment Center source or slot; otherwise investigate runtime environment variables and entrypoint.

2026-07-03 — Admin Panel Rebuild verification
- Sidebar shows Scopes and Categories links under Admin.
- Able to create a Scope, then a Category under it, then a Form under that Category.
- New form initializes with Subject/Description/Attachments fields.
- Edit Form allows adding a custom field that appears between Subject and Description and supports drag re-order within custom zone.
- Forms list includes Delete with confirmation; delete performs soft delete and hides the form from the list.

2026-07-03 — User-facing flows + navigation improvements
- Tom Select (v2.3.1) searchable dropdown library added to base.html (CSS in <head>, JS before </body>).
- Request Creation Flow rebuilt as 3-step selection: Scope → Category → Form.
  - Single-scope users auto-select and skip scope picker; multi-scope users see scope buttons.
  - Category and Form dropdowns are Tom Select searchable widgets loaded via JSON endpoints
    (/requester/api/categories?scope_id=X and /requester/api/forms?scope_id=X&category_id=Y).
  - If a scope has no categories, the category step is skipped and un-categorized forms are shown.
  - Dynamic form fields rendered from /api/form-fields/<id>; Subject value stored in ticket.subject.
- User scopes shown as pill badges in the top navbar for all authenticated roles (base.html).
- Approver Request History: new route /approver/request-history with status/scope/date filters,
  50-per-page pagination, and new template approver/request_history.html with Export to Excel.
- Approver Approval History: rebuilt template with dynamic scope dropdown (from active_scopes),
  Export to Excel button wired to /approver/approval-history/export, and column alignment matching queue.html
  (Ticket# | Raised By | Issue Type | Subject | Resolved Date | Scope | Status).
- Admin All Tickets: added Scope filter dropdown (populated from active_scopes), date-range filters,
  and Export to Excel button wired to new /admin/tickets/export route using standardized columns
  (Ticket#, Subject, Form Name, Scope, Raised By, Assigned To, Status, Created Date, Resolved Date).
- Dynamic Approver Queue tabs: /approver/queue/<scope_name> route generates tabs from active Scope records;
  legacy /approver/queue/ar and /approver/queue/gl redirect to the dynamic route.
- Sidebar links: Approver sidebar has "Request History"; Admin sidebar has "Request History" → /admin/tickets.
- Export routes consolidated: requester history/my-requests, approver history/approval-history, admin tickets
  all use the shared _export_build_workbook helper from requester.py for consistent Excel columns.
