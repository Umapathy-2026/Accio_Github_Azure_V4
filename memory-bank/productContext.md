Why this project exists and what problem it solves
ACCIO replaces scattered email/Excel workflows for Finance Accounts Receivable with a centralized, auditable ticketing and approval system. It standardizes request intake via configurable forms, enforces clear approval chains, and maintains complete history for compliance and audit.

How it should behave from a user's perspective
- Requester: signs in, selects an issue type (form), fills dynamic fields, attaches evidence, and submits. Sees ticket status on a dashboard and receives notifications when approvers act or ask for clarification.
- Approver: sees an assigned queue (AR/GL scope aware), reviews ticket details and attachments, approves/rejects/sends back with comment. Can reassign to another approver with audit trail.
- Admin: manages users/roles/scopes, creates/edits forms and fields, exports tickets and audit logs, and views dashboard metrics.

Key workflows
- Ticket flow: Submit → Pending → Under Review → (Approved → Sent to Fulfilment) or Rejected or Needs Clarification → Clarification Provided → Under Review → …
- VAT/Invoice flows: Captured as specific IssueForm configurations; payload stored as JSON per ticket.
- Approval chain: Requester’s manager (or first active approver fallback) receives notifications; actions logged in ApprovalLog and Notification.