# Security and privacy readiness

Phase 7C provides a versioned local-development assessment. It is evidence
for engineering release decisions, not HIPAA, SOC 2, or production security
certification.

FastAPI owns authentication, RBAC, dataset grants, CSRF checks, request
limits, and error redaction. MCP remains an independent authentication,
tool-allowlist, and dataset-authorization boundary; browser cookies and
tokens are never forwarded. Temporal owns durable orchestration only and
does not authorize reviewers. PostgreSQL stores application records and
append-only access decisions. Telemetry never replaces audit tables.

Run `make security-scan` for a sanitized report. Secret, privacy, dependency,
static-analysis, and container checks emit only categories and locations. A
missing scanner is `not_evaluable`, never a pass. Run
`make audit-integrity-verify` to verify the SHA-256 chain for newly written
access decisions; historical records without integrity fields remain
`legacy_unverified` and are not rewritten.

`make retention-dry-run` prints the source-controlled retention policy and
performs no deletion. Any future deletion must name one category and bounded
date range, show a dry-run preview, require explicit confirmation, be
authorized, and create an access-decision audit record.

The identity provider, secrets, model runtime, and data are development-only.
Production would require an external secret manager, short-lived credentials,
rotation, revocation, HTTPS, Secure cookies, and an externally protected
immutable audit sink.
