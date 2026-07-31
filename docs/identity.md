# Phase 6A — Identity and access governance

The platform has a local-only OIDC-compatible identity boundary. The
development issuer is served by FastAPI at `/local-oidc`; login creates a
short-lived HttpOnly, SameSite session cookie containing a signed JWT with
validated issuer, audience, subject, and expiry claims. This is an identity
simulation, not hospital SSO, OAuth federation, HIPAA, or production
authentication.

Authentication is separate from authorization. The application owns the
database-backed RBAC permission matrix and dataset grants. MCP remains a
separate service-authentication boundary and browser tokens are never
forwarded to MCP. Temporal review signals are accepted only after FastAPI
validates the session, permission, dataset grant, reviewer assignment, enabled
state, and separation of duties, then persists the application decision.

Local users are selected from a server-side allowlist (`IDENTITY_DEV_USERS` or
the built-in development profiles). Roles are never taken from browser
arguments. The legacy `X-Actor-Id` bridge remains enabled only for local
development and ignores `X-Actor-Role`; set
`IDENTITY_LEGACY_HEADERS_ENABLED=false` to require sessions or bearer tokens.
Cookie-authenticated state-changing requests also require a configured local
`Origin`; this is the development CSRF defense layered with `HttpOnly` and
`SameSite=Lax` cookies. Bearer clients are not browser-cookie requests.

Roles are `researcher`, `reviewer`, `governance_officer`,
`platform_operator`, `auditor`, and `administrator`. Synthetic dataset grants
and reviewer assignments are persisted. Local bootstrap grants existing
synthetic datasets to the selected development identity so the local console
remains usable. Only the reviewer profile is assigned reviewer datasets
automatically; administrators do not receive review authority implicitly.
Production would require explicit administrative grant workflows.

Endpoints:

- `POST /api/v1/auth/login` — local development login
- `POST /api/v1/auth/logout` — clear the session cookie
- `GET /api/v1/auth/me` — current identity, permissions, and dataset grants
- `GET /local-oidc/.well-known/openid-configuration` — bounded local metadata
- `GET /api/v1/identity/users` — administrator-only local identity inspection

Protected APIs return 401 for missing/invalid sessions and 403 for denied
permissions or datasets. Access decisions are append-only in
`identity_access_decisions`; tokens, passwords, headers, and complete IdP
claims are not persisted. The frontend `/login` and `/identity` pages are
development-only. Review endpoints use a separate policy path: creators may
inspect their own pending review, while only an enabled, dataset-authorized,
explicitly assigned reviewer with both `review:read-assigned` and
`review:decide` may inspect or decide another user's review. Normal run
ownership checks are unchanged. Backend authorization remains authoritative.

Run the bounded local validation matrix with:

```sh
make identity-validate
```

The runner discovers the OpenAPI routes, uses ephemeral cookie jars, applies
reversible local grant/disabled-user fixtures, validates review and dataset
boundaries, and writes sanitized reports under the ignored
`evaluation_outputs/identity/` directory.
