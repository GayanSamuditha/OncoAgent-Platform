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
