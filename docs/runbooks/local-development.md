# Local Development Runbook

```bash
cp .env.example .env
make install
make db-up
make migrate
make backend-dev
make frontend-dev
```

Use `make check` before handoff. Stop with `make db-down`; use `docker compose -f infra/docker-compose.yml down -v` only when the local database volume is intentionally disposable.
