# Phase 5C resilience certification

The resilience certification layer is a local, synthetic-data-only
validation harness around the existing Temporal-managed CrewAI workflow. It
does not alter LangGraph, CrewAI, MCP authorization, retrieval, governance,
or human-review policy.

## Scenario registry

The versioned registry is in `apps/api/app/resilience/registry.py` and covers
worker interruption, Ollama and MCP retryable failures, API and Temporal
restarts, Activity and review cancellation, idempotency, policy denials, and
Temporal unavailability.

## Running certification

```bash
make resilience-certify
make resilience-certify SCENARIO=activity-cancellation
make resilience-report
```

The runner accepts observed run IDs and validates application records,
Temporal history, audit events, MCP lineage, direct Tempo trace lookup, and
redaction. Reports are written to ignored `evaluation_outputs/resilience/`.
No browser endpoint can trigger fault injection.

## Fault boundaries

Development-only fault controls are allowlisted, one-shot, local/test-only,
and disabled by default. They accept a stage and a bounded failure category,
never code or shell input. Activity cancellation uses safe heartbeat
checkpoints and records only bounded progress metadata. It does not claim
recovery at a model token boundary.

## Gates

The scorecard keeps retryable recovery, policy non-retry, duplicate records,
cancellation finalization prevention, review durability, audit completeness,
MCP correlation, trace retrieval, and telemetry redaction as separate gates.
N/A scenarios are not counted as passing observations.

This is local synthetic development validation, not clinical validation,
regulatory certification, or production SLO evidence.
