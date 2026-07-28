# Phase 5A observability

This phase adds local OpenTelemetry tracing, Prometheus-compatible metrics,
Grafana Tempo trace storage, Grafana dashboards, and structured JSON logs.
It is operational telemetry only; the existing workflow, MCP, provenance, and
audit tables remain authoritative and telemetry never replaces them.

## Local stack

```bash
docker compose -f infra/docker-compose.yml up -d postgres otel-collector prometheus tempo grafana
```

| Component | Local endpoint |
| --- | --- |
| API metrics | http://127.0.0.1:8000/metrics |
| Collector OTLP gRPC | http://127.0.0.1:4317 |
| Prometheus | http://127.0.0.1:9090 |
| Tempo | http://127.0.0.1:3200 |
| Grafana | http://127.0.0.1:3001 |

The Collector sends traces to Tempo and exposes OTLP metrics in a
Prometheus-scrapable endpoint. API applications remain functional when the
Collector is down or `OBSERVABILITY_ENABLED=false`. Bindings are localhost
only and Docker resource limits are intentionally conservative for a 24 GB
Apple silicon development machine.

## Privacy and cardinality

Trace and metric names are low-cardinality. Patient IDs, run IDs, prompts,
queries, raw FHIR, credentials, authorization headers, model thinking, and
cache paths are never metric labels or structured log fields. Logs include
trace and span IDs when available, but audit records remain the institutional
record. Trace IDs are correlation metadata, not authorization credentials.

## Instrumentation

The official OpenTelemetry FastAPI instrumentation owns inbound HTTP spans.
The application middleware only records bounded request metrics and reads the
current span for a safe response trace header; it never attaches or detaches
OpenTelemetry context. Dependency generators likewise do not hold manual span
contexts across `yield`. Workflow, CrewAI, and MCP service boundaries create execution spans;
application audit rows persist nullable trace and span IDs through migration
0010. Retrieval and model integrations expose safe provider, duration, status,
fallback, and token-count dimensions only where available.

Development alert rules cover API errors, workflow failures, orphan MCP
requests, and governance-gate failures. They are not production SLOs and no
external notification service is configured.

## Validation

```bash
docker compose -f infra/docker-compose.yml config
curl -s http://127.0.0.1:8000/api/v1/observability/status
curl -s http://127.0.0.1:8000/metrics
```

Telemetry export is best-effort. A failed exporter must not fail a clinical
workflow, while audit persistence and governance validation continue to be
handled independently.
