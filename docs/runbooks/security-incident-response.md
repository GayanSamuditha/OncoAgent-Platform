# Security incident readiness runbook

This is a local-development checklist, not a staffed incident response plan.
For credential exposure, unauthorized dataset access, self-approval, MCP
misuse, audit-integrity failure, dependency vulnerability, prompt injection,
worker/database compromise, backup exposure, telemetry leakage, denial of
service, or release-gate bypass:

1. Stop the affected workflow or service and preserve run, Temporal, MCP,
   audit, and trace identifiers.
2. Disable or rotate the affected development identity or service credential;
   never paste a credential into an issue or report.
3. Revoke active sessions and reviewer assignments when authorization may be
   stale.
4. Verify dataset, tool, reviewer, and release gates before resuming.
5. Run `make audit-integrity-verify`, `make privacy-scan`, and relevant
   resilience/release checks.
6. Preserve sanitized evidence and document containment, recovery,
   verification, and a post-incident review.

No production contacts or regulatory notification claims are included.
