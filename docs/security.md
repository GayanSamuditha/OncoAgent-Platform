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
static-analysis, and container checks emit only counts, tool versions, and
locations. A missing optional scanner is `not_evaluable`, never a pass;
malformed output, timeouts, and unexpected exits are `error`. Run
`make audit-integrity-verify` to verify the SHA-256 chain for newly written
access decisions; historical records without integrity fields remain
`legacy_unverified` and are not rewritten.

`make security-verify` runs every required subcheck and aggregates their exit
status, so a dependency failure cannot hide an audit-integrity failure.

`make security-tools-install` is the explicit setup step for the pinned
Bandit, pip-audit, Trivy, and web dependency tooling. It may download
dependencies and the pinned Trivy image; normal startup never does so.
`make ollama-check` is separate from security scanning and verifies the exact
configured model tag. `make ollama-prepare` starts Ollama or downloads a model
only after `CONFIRM_OLLAMA_SETUP=YES` is supplied.

To create a clean verification baseline without modifying historical evidence,
run `CONFIRM_VALIDATION_CREATE=YES make validation-create`. The command stops
currently running application writers, writes a timestamped SQL backup and
manifest, verifies its SHA-256 checksum, restores it into an exact temporary
database, and only then starts a separately named validation Compose project
and volume. Writer services are restarted from a finally-style cleanup path on
success or failure. The original PostgreSQL volume is never removed.

`make retention-dry-run` prints the source-controlled retention policy and
performs no deletion. Any future deletion must name one category and bounded
date range, show a dry-run preview, require explicit confirmation, be
authorized, and create an access-decision audit record.

The identity provider, secrets, model runtime, and data are development-only.
Production would require an external secret manager, short-lived credentials,
rotation, revocation, HTTPS, Secure cookies, and an externally protected
immutable audit sink.
