# Phase 7B — performance and reliability

This is a bounded, local-development measurement layer for OncoAgent (contract
version 7B.2). It uses
synthetic Synthea data only and does not establish clinical, production, or
capacity claims. Profiles are versioned in `apps/api/app/performance/profiles.py`;
the runner is `scripts/performance_runner.py`.

## Quick start

```bash
make performance-smoke
make performance-run PROFILE=api-read-concurrent
make performance-report
```

Reports are JSON and Markdown under `evaluation_outputs/performance/` and are
ignored by Git. The runner is limited to local/test environments, uses bounded
async concurrency, and never prints cookies, tokens, prompts, FHIR, or model
outputs. Policy denials are expected outcomes rather than infrastructure
failures. Empty denominators remain `not_evaluable`.

## Workload integrity

`api-read-light` and `api-read-concurrent` measure only their documented
health/readiness operations. The other registered profiles use named adapters:

- `langgraph-cohort`: authenticated governed run, approval, and terminal poll.
- `crewai-temporal`: Temporal-backed CrewAI run, review, and terminal poll.
- `mcp-read`: allowlisted Streamable HTTP MCP tool calls with service identity.
- `model-saturation`: bounded Ollama `/api/generate` calls (maximum two in flight).
- `cancellation-load`: authenticated CrewAI cancellation and state check.
- `mixed-platform`: bounded API, LangGraph, and CrewAI operations.
- `database-pressure`: authenticated database-backed performance-history reads.
- `authorization-denial`: expected researcher audit-access denials.

`retry-recovery` is `not_evaluable` unless an external local/test runner has
explicitly enabled the existing one-shot allowlisted fault injection. It is
never simulated by health probes. Any unsupported or zero-operation profile is
reported as `not_evaluable`, and the CLI returns nonzero. The report records the
adapter, actual operation count, success/denial/failure counts, and reason.

## Controls and SLOs

Default local controls favor reliability: API workflow concurrency 1, CrewAI
concurrency 1, Ollama concurrency 1, bounded database pool (5 plus 5
overflow), and a finite queue wait. Overload must be explicit (429/503) and
never bypass authorization or create duplicate work. Correctness SLOs are
blocking: zero authorization bypass, zero duplicate business records, zero
orphan MCP requests, zero cancellation finalization, zero policy-denial
retries, and zero telemetry redaction violations. Latency and throughput are
informational unless explicitly configured as blocking.

The performance API is read-only and requires the existing `evaluation:read`
permission:

- `GET /api/v1/performance`
- `GET /api/v1/performance/policy`
- `GET /api/v1/performance/executions/{execution_id}`
- `GET /api/v1/performance/executions/{execution_id}/metrics`
- `GET /api/v1/performance/executions/{execution_id}/slos`

Migration `0014_performance_reliability` stores sanitized aggregate metadata;
detailed reports stay ignored. No framework topology, governance rule,
retrieval policy, MCP contract, or human-review behavior is changed.

Performance reports can be referenced by release-evaluation artifacts through
their sanitized `report_reference`. Correctness SLOs remain eligible for the
existing release-gate review; hardware-specific latency and throughput remain
informational unless a release candidate explicitly opts into local latency
gates. No performance result silently overrides a release decision.
