# Local Development Runbook

```bash
cp .env.example .env
make install
# Optional downstream CrewAI integration:
# make crewai-install
make db-up
make migrate
make backend-dev
make frontend-dev
```

For durable CrewAI execution, set `CREWAI_EXECUTION_MODE=temporal`, then run
the isolated local Temporal services and worker:

```bash
make temporal-up
make temporal-status
make temporal-worker
curl -sS -H 'X-Actor-Id: admin' -H 'X-Actor-Role: admin' \
  http://127.0.0.1:8000/api/v1/temporal/status
```

`temporal-schema-init` uses `temporalio/admin-tools:1.31.2` to idempotently
create and upgrade the isolated core and visibility schemas before the
`temporalio/server:1.31.2` service starts. The namespace-init job creates the
development `oncoagent` namespace once. Temporal server persistence is
separate from the OncoAgent application PostgreSQL schema. Stop it with
`make temporal-down`. If the API reports
Temporal unavailable, it returns 503 and does not silently use the legacy
worker. Use `CREWAI_EXECUTION_MODE=legacy` only for explicit rollback tests.

Use `make check` before handoff. Stop with `make db-down`; use `docker compose -f infra/docker-compose.yml down -v` only when the local database volume is intentionally disposable.
