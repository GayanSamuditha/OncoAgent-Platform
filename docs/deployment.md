# Local deployment and operations

Phase 7A provides a reproducible Docker Compose development stack. It is
local-only, uses synthetic Synthea data, and is not clinically validated or
production deployment infrastructure.

## Quick start

```bash
cp .env.example .env
make validate-config
make platform-up
make migrate
make verify-platform
```

`make platform-up` uses the `full` profile and builds the API/MCP/Temporal
worker and Next.js images. Ollama remains host-based on Apple Silicon; set
`LOCAL_LLM_BASE_URL` and `CREWAI_OLLAMA_BASE_URL` to its host endpoint. The
recommended profile disables legacy identity headers and development fault
injection. It also keeps CrewAI disabled until MCP service credentials and a
synthetic dataset allowlist are configured; `make demo-up` prepares those local
demo settings before enabling the integration.

## Profiles and endpoints

The unprofiled services are the core stack: application PostgreSQL, the
migration job, FastAPI, MCP, and the frontend. `temporal` adds Temporal
PostgreSQL, idempotent schema/namespace jobs, the server, UI, and Activity
worker. `observability` adds Collector, Prometheus, Tempo, and Grafana.
`evaluation` provides an optional bounded runner image. `full` enables all
profiles. The `models` capability is host-based and intentionally has no
Ollama container.

| Service | Local endpoint |
|---|---|
| Web | http://127.0.0.1:3000 |
| FastAPI | http://127.0.0.1:8000 |
| MCP | http://127.0.0.1:8010/mcp |
| PostgreSQL | 127.0.0.1:55432 |
| Temporal | 127.0.0.1:7233 |
| Temporal UI | http://127.0.0.1:8233 |
| Prometheus | http://127.0.0.1:9090 |
| Tempo | http://127.0.0.1:3200 |
| Grafana | http://127.0.0.1:3001 |

Startup is ordered by PostgreSQL health, application Alembic migration,
Temporal schema and namespace initialization, API/MCP readiness, worker, and
frontend. Observability is optional for core readiness and telemetry failure
never fails a workflow.

## Data and operations

`make seed-synthetic` requires an explicit `SYNTHEA_ARCHIVE` and invokes the
existing bounded importer. It never downloads data. `make verify-data` checks
dataset presence and patient counts without printing clinical records.

Use `make platform-status`, `make platform-logs`, and `make verify-platform`
for bounded inspection. `make platform-clean` preserves volumes by default;
destructive volume removal requires `ALLOW_DESTRUCTIVE_CLEAN=1`.

Do not use destructive Compose or Docker-wide cleanup commands. For a clean
security baseline, use the isolated `validation-create` workflow instead. It
backs up and verifies the running `oncoagent` application database, then uses
a separate timestamped Compose project and PostgreSQL volume. Use
`make validation-down VALIDATION_PROJECT=<exact-project>` to stop that project;
it does not remove volumes.

Generated test/build reports can be previewed with
`make artifacts-clean-dry-run`. Applying the explicit repository-relative
allowlist requires `CONFIRM_ARTIFACT_CLEAN=YES make artifacts-clean`; secrets,
backups, raw Synthea data, model files, audit evidence, uploads, and Docker
volumes are protected.

`make backup-databases BACKUP_DIR=backups/<name>` writes ignored SQL dumps for
application and, when running, Temporal PostgreSQL. Restore requires both an
explicit `BACKUP_DIR` and `CONFIRM_RESTORE=YES`. Do not back up credentials,
cookies, model caches, raw FHIR, or telemetry volumes.

The Compose limits are development defaults for a constrained Apple Silicon
MacBook, not capacity or production SLO claims. Containers run as non-root
where applicable, bind administrative ports to localhost, and do not mount a
Docker socket or host data directories.
