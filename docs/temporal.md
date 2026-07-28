# Phase 5B — Temporal durable CrewAI execution

Temporal is the durable lifecycle coordinator for the downstream CrewAI
research workflow. It is not an agent framework and does not replace
LangGraph, MCP, PostgreSQL audit persistence, or human review.

## Local versions

- Temporal Python SDK: `1.30.0` (Python 3.12, Apple Silicon wheel)
- Temporal server image: `temporalio/server:1.31.2`
- Temporal admin-tools image: `temporalio/admin-tools:1.31.2`
- Temporal UI image: `temporalio/ui:2.52.1`
- Namespace: `oncoagent`
- Task queue: `oncoagent-crewai`
- Server: `127.0.0.1:7233`
- UI: `http://127.0.0.1:8233`

These are localhost-only development services. They are not production
deployment or clinical infrastructure.

## Ownership

- LangGraph owns the first-party governed cohort graph and PostgreSQL
  checkpoint state.
- CrewAI owns the four-agent sequential research process.
- Temporal owns durable workflow lifecycle, retries, heartbeats, signals,
  cancellation, and safe Activity boundaries.
- MCP owns authentication, authorization, dataset isolation, tool limits,
  retrieval policy, and structured clinical access.
- PostgreSQL owns application records, audit events, evidence, and lineage.

The CrewAI agent sequence remains one Activity boundary because CrewAI does
not expose stable task-resume hooks. Recovery is from the last completed
Temporal Activity, not from a token-generation position.

## Start and validate

```bash
make temporal-up
make temporal-status
make temporal-worker
```

`temporal-schema-init` is a one-shot, idempotent service using the pinned
admin-tools image. It creates the separate `temporal` and
`temporal_visibility` databases when needed, initializes both schema version
tables, and applies all versioned PostgreSQL schema updates. The Temporal
server depends on successful completion of this service and runs with
`SKIP_SCHEMA_SETUP=true`; restarts therefore do not recreate or delete
workflow history. `temporal-namespace-init` creates the `oncoagent` namespace
only when it does not already exist.

Run the API with `CREWAI_EXECUTION_MODE=temporal`. If Temporal is unavailable,
the API returns a typed 503 and does not silently use legacy mode.

```bash
make migrate
curl -sS -H 'X-Actor-Id: admin' -H 'X-Actor-Role: admin' \
  http://127.0.0.1:8000/api/v1/temporal/status
```

Stop local services with `make temporal-down`. Temporal persistence uses a
separate named PostgreSQL volume and never uses the OncoAgent application
schema. `make temporal-schema` can be used to rerun the schema job explicitly.

## Retry and review behavior

Transient Ollama, MCP transport, PostgreSQL, timeout, and worker failures may
receive bounded Activity retries. Safety, authorization, dataset, schema,
unsupported-operation, and governance failures are non-retryable.

The workflow creates exactly one review record, waits durably for a validated
review signal, and applies the decision through an Activity. Duplicate or
conflicting decisions are rejected by the existing application policy.

Cancellation is signaled to the workflow, persisted as a terminal decision,
and prevents finalization. Temporal event history is not copied into
application tables; PostgreSQL stores safe business and audit summaries.

## Legacy rollback mode

Set `CREWAI_EXECUTION_MODE=legacy` explicitly to use the prior bounded local
worker for comparison or rollback. Legacy execution is not durable across a
process failure. No automatic fallback occurs from Temporal to legacy mode.

## Development-only fault validation

For deterministic local validation only, the Activity worker accepts a
bounded allowlisted fault configuration through environment variables:

```bash
TEMPORAL_DEV_FAULT_STAGE=execute_crewai_pipeline \
TEMPORAL_DEV_FAULT_CATEGORY=ollama_unavailable \
TEMPORAL_DEV_FAULT_ATTEMPTS=1 \
make temporal-worker
```

Supported categories are `ollama_unavailable`, `mcp_transport_failure`,
`postgresql_transient_failure`, `worker_interrupted`, and `bounded_timeout`.
The controls are active only for `local` or `test` environments, fail only
the configured Activity attempt, accept no code or arbitrary command, and
are disabled by default. A bounded delay can be set with
`TEMPORAL_DEV_ACTIVITY_DELAY_SECONDS` to validate worker interruption or
in-Activity cancellation. These controls are not production configuration
and do not bypass MCP authorization or governance.

An in-flight cancellation is observed at the next safe Activity checkpoint
or immediately after the bounded CrewAI call returns. Partial business
records remain inspectable; finalization is prevented. Recovery is never
claimed at a token-generation position.
