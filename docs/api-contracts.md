# Phase 0 API Contracts

## `GET /health`

Returns HTTP 200 when the API process is running. It does not query PostgreSQL.

```json
{"status":"ok","service":"OncoAgent Platform API","version":"0.1.0"}
```

## `GET /ready`

Queries PostgreSQL with `SELECT 1`. It returns HTTP 200 with `status: ready` when available and HTTP 503 with `status: not_ready` when unavailable.

## `GET /api/v1/platform/info`

Returns platform identity, the synthetic-only policy, the not-clinically-validated status, and separate implemented/planned capability lists.

## Phase 3A workflow contracts

Workflow endpoints require development-only `X-Actor-Id` and `X-Actor-Role` headers. Roles are `researcher`, `reviewer`, and `admin`; these headers do not provide production authentication.

- `POST /api/v1/runs` creates a bounded run and returns `run_id`, `thread_id`, status, and links.
- `GET /api/v1/runs/{run_id}` returns inspectable status, plan, approval, warnings, errors, and final result metadata.
- `GET /api/v1/runs/{run_id}/events`, `/evidence`, and `/candidates` return bounded paginated audit data.
- `GET /api/v1/runs/{run_id}/stream` emits safe workflow events only; it never emits private reasoning.
- `POST /api/v1/approvals/{approval_id}/decision` accepts `approve`, `reject`, `request_changes`, or `cancel`. Approve/reject/request-changes decisions require reviewer/admin and approval cannot be made by the initiating researcher.
- `POST /api/v1/runs/{run_id}/cancel` cancels a pending run subject to actor policy.
- `GET /api/v1/audit-events` and `GET /api/v1/workflow-policy` expose audit inspection and current execution controls.

Workflow retrieval uses MedCPT, then BioClinicalBERT, then PostgreSQL FTS. The cross-encoder is not enabled automatically. Retrieved candidates are never final cohort members until normalized structured FHIR verification succeeds and a reviewer approves the interrupted run.

## Phase 3B local planning and operations

`GET /api/v1/models/planners`, `/models/planners/{provider_id}`, and
`/models/local-runtime` report Qwen/Ollama availability without loading the
model. `POST /api/v1/models/planners/qwen_local/smoke-test` is an admin-only,
synthetic schema smoke test. Run creation accepts `planner_provider` values
`auto`, `qwen_local`, and `deterministic`; `auto` records a Qwen attempt and
falls back to the deterministic planner when needed. Run responses expose
structured planner lineage, never hidden reasoning.

The local console routes are `/workflow`, `/approvals`, `/audit`, and
`/agent-catalog`. All displays are synthetic development views and not
clinical validation.

## Phase 4A MCP inspection contracts

- `GET /api/v1/mcp/status` reports enabled transports and the read-only tool catalog.
- `GET /api/v1/mcp/clients` reports sanitized development client identities and dataset scopes; tokens are never returned.
- `GET /api/v1/mcp/tools` reports stable tool names and versions.
- `GET /api/v1/mcp/requests` and `/mcp/requests/{request_id}` report bounded MCP audit lineage.

The MCP Streamable HTTP endpoint is `/mcp` on the separately started
localhost gateway. Stdio uses `MCP_STDIO_CLIENT_ID` and `MCP_STDIO_TOKEN` for
local integration. Tool arguments use a strict `request` object matching the
registered Pydantic input contract. Results include typed safe error objects,
synthetic-data notices, and no raw FHIR payloads.

## Phase 4B CrewAI contracts

- `GET /api/v1/crews`, `/crews/oncology-research`, and `/crews/oncology-research/status` expose downstream-client configuration without credentials.
- `POST /api/v1/crews/oncology-research/runs` accepts a strict dataset-scoped request and returns `202`; it does not accept MCP URLs/tokens, arbitrary models/tools, SQL, paths, or approval decisions.
- Run inspection is available at `/crews/oncology-research/runs/{run_id}`, `/events`, `/tasks`, and `/output`; output excludes scratchpads and raw FHIR.
- `POST /crews/oncology-research/runs/{run_id}/review` accepts only the documented synthetic-research review decisions. Only reviewer/admin roles may decide, and the initiating researcher cannot accept their own run. Duplicate decisions return `409`.
## Identity

Protected APIs accept the local OIDC-compatible HttpOnly session created by
`POST /api/v1/auth/login`; bearer tokens with validated issuer, audience, and
expiry are also supported. `GET /api/v1/auth/me` returns the server-resolved
role, permissions, and synthetic dataset grants. Missing authentication is
401; authenticated permission or dataset denial is 403. The legacy actor
headers are local-only compatibility and the role header is ignored.
