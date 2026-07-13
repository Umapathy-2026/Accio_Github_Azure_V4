ompleted and working
- Core authentication (login/logout, CSRF tokens, password strength checks, lockout)
- Ticket creation with dynamic IssueForm fields and attachments
- Approver queues and actions (approve/reject/send back/reassign)
- Admin console (dashboard metrics, user management, form CRUD, audit log)
- Email notifications on ticket creation and clarification (best-effort)
- Excel exports for tickets and audit logs
- Rate limiting with sane defaults
- Fixed duplicate ORDER BY bug on SQL Server (2026-07-02) — replaced `ticket.approval_logs.order_by()` with `ApprovalLog.query.filter_by()` in three call sites to avoid duplicate columns in ORDER BY that SQL Server rejects.
- Fixed "Approve All"/"Reject All" buttons — added CSRF token to fetch headers in queue.html
- Fixed file upload UI — no visual feedback when file selected (replaced broken `handleFileSelect()` with direct DOM manipulation in new_ticket.html)
 - Admin panel rebuild (2026-07-03):
   - Scope management (list/create/toggle with block + warning if active forms exist)
   - Category management (grouped by scope, create with scope selection, toggle with same guard)
   - Form management: create with active scope dropdown and optional category; default fields from DEFAULT_FORM_FIELDS; forms list shows scope/category and includes Delete (soft delete); edit view locks protected fields and allows adding/reordering custom fields between Subject and Description
   - User management: create/edit with multi-select scope access (UserScope), approver_id label updates (Assigned Approver)
   - Deactivate approver flow: check returns subordinates_count/subordinates, UI forces reassignment to new approver; backend reassigns users, then tickets, then deactivates

In progress
- Azure deployment verification: Confirmed commit c237afae (Fixes2) includes migration switch to upgrade() and adds 0002 migration. Pushed no-op commit 7e9998f to trigger clean redeploy. GitHub Actions run #10 (head_sha 7e9998f) completed successfully deploying to accio-demo. Awaiting Azure App Service startup log to confirm Alembic upgrade 0001 -> 0002 on boot.

2026-07-06 — Three targeted fixes applied
- new_ticket.html: .scope_id → .id, .scope.name → .name (Scope objects, not UserScope)
- api.py: added current_app to Flask import
- admin.py: removed duplicate export_tickets() route (/admin/export), kept export_tickets_standard() at /admin/tickets/export

2026-07-06 — azure-pipelines.yml created
- Build stage: Python 3.12, pip install, zip artifact (excludes __pycache__, .git, instance/)
- Deploy stage: AzureWebApp@1 to Linux App Service with startup.sh
- GitHub mirror step pushes Fixes2 branch to Umapathy-2026/ACCIO-AzureDevops-mirror
- Committed as 58b8cb8 "ci: add Azure Pipelines configuration with GitHub mirror"

2026-07-07 — Cosmetic admin sidebar reorder
- base.html: Admin "Request History" nav item moved from between "All Tickets" and "Audit Log" to below the divider, after "My Requests". Purely cosmetic; no routes/links changed.

2026-07-07 — Login page glassmorphic UI overhaul (split-screen layout)
- auth/login.html: Complete front-end redesign (no backend changes)
  - Split-screen: LEFT half = large logo panel with glassmorphic background (rgba + backdrop-filter blur(20px)); RIGHT half = floating glassmorphic login credentials card
  - LEFT logo panel: 320px 3D elevated logo with perspective wrapper, layered drop-shadows (depth + brand glow), continuous rotateY/rotateX wobble (5s), pulsing radial glow, continuous shine sweep (diagonal gradient highlight, infinite 3.5s loop), brand text "ACCIO" below
  - RIGHT form panel: floating glassmorphic card (rgba(255,255,255,0.06) + backdrop-filter blur(24px) saturate(180%), soft border, inset highlight, gentle float animation)
  - Animated gradient background: 3 shifting radial-gradient layers (brand teal/cyan) on 18s loop + 3 floating blurred orbs
  - Mouse-following particles (Antigravity-style): full-screen <canvas>, vanilla JS, glowing teal/cyan particles spawn at cursor on mousemove/touchmove, fade+shrink with gravity, max 130 particles, requestAnimationFrame
  - Glass-themed inputs, gradient submit button, glass Microsoft SSO button (Entra mode preserved)
  - All Flask/Jinja logic preserved: CSRF token, auth_mode conditional, form actions, forgot-password link
  - Accessibility: prefers-reduced-motion disables all animations; responsive: panels stack vertically on < 768px, reduced sizing on < 480px
  - Note: inline <style>/<script> acceptable until CSP Phase 3 (future: externalize JS with nonce)

2026-07-07 — App-wide glassmorphic dark theme (base.html overhaul)
- base.html: Complete CSS overhaul from light to dark glassmorphic theme
  - CSS variables: --bg #0e1830, --surface rgba(255,255,255,0.06), --text #ffffff, --primary #14b8a6
  - Animated gradient background (.app-bg) + 3 floating blurred orbs added to all authenticated pages
  - Particle canvas (#particle-canvas) with mouse-following JS on all pages (max 100 particles)
  - Header, sidebar, cards, tables, inputs, buttons, modals, toasts, notifications, filter bar, pagination, bulk bar: all glassmorphic dark
  - Badges: translucent dark variants; Tom Select: dark theme CSS overrides
  - All text colors switched to white/light variants for dark background
  - All Flask/Jinja logic and JS functions preserved unchanged
  - Look is now consistent with the login page across the entire application

2026-07-06 — Microsoft Entra ID (Model B JIT) + email dev mode + branding fixes
- requirements.txt: msal==1.28.0 added
- models.py: User.entra_oid (String(36), unique, indexed); password_hash server_default='' for Entra-only users
- migration 0003_add_entra_oid_to_users.py created (revises 0002)
- __init__.py: AUTH_MODE/ENTRA_* config + MAIL_DEV_MODE + MAIL_SERVER/PORT env overrides
- email.py: dev mode logs [DEV EMAIL — NOT SENT]; 5x "Finance AR Ticketing System" → "ACCIO Finance Approval System"; send_password_reset() added
- auth.py: full Entra ID implementation (entra_login, entra_callback JIT, entra-aware logout/forgot/force-change); local login passes auth_mode to template
- login.html: auth_mode == 'entra' shows Microsoft SSO button; else shows local form
- users.html: "Needs Setup" badge; "Create User" → "Add User Manually" (button/modal/submit); SSO auto-provisioning warning
- Boot test could not run (Flask not installed in local env, pip blocked by Application Control policy); all file-based verifications passed

Not yet started / potential roadmap
- Move rate-limit storage to Redis for production scale-out
- Introduce Alembic for database migrations
- Add unit/integration tests for core flows
- Improve attachment virus scanning and content-type validation
- Enhance dashboards with charts and filters
 - Enhance dashboards with charts and filters

2026-07-03 — Admin panel rebuild verification completed
- Verified that Scopes and Categories navigation links are present in sidebar.
- Confirmed scope/category management routes and templates work with deactivation guards.
- Forms: creation uses active scopes only; default fields copied; edit locks protected fields and inserts custom fields at index 1; list shows scope/category and supports soft delete.
- Users: multi-scope access via checkboxes; labels updated to "Assigned Approver".
- Deactivate approver flow: deactivate-check returns subordinates; modal requires new approver; backend reassigns users, then tickets, then deactivates.

2026-07-03 — User-facing flows + navigation improvements completed
- Tom Select (v2.3.1) searchable dropdown library integrated into base.html.
- Request Creation Flow: 3-step Scope → Category → Form selection with Tom Select searchable dropdowns;
  single-scope users auto-select; JSON endpoints for categories and forms; dynamic field rendering.
- User scope badges displayed as pills in the top navbar for all authenticated roles.
- Approver Request History: new /approver/request-history route + template with status/scope/date filters,
  50-per-page pagination, and Export to Excel.
- Approver Approval History: rebuilt with dynamic scope dropdown, Export to Excel button, and column
  alignment consistent with queue.html (Ticket# | Raised By | Issue Type | Subject | Resolved Date | Scope | Status).
- Admin All Tickets: added Scope filter dropdown (from active_scopes), date-range filters, and Export to Excel
  wired to new /admin/tickets/export route using standardized columns via _export_build_workbook helper.
- Dynamic Approver Queue tabs generated from active Scope records; legacy /queue/ar and /queue/gl redirect
  to /approver/queue/<scope_name>.
- Sidebar links added: Approver "Request History" and Admin "Request History" (→ /admin/tickets).
- All export routes (requester history/my-requests, approver history/approval-history, admin tickets) now
  use the shared _export_build_workbook helper for consistent Excel columns.
