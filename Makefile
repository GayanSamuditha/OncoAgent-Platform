SHELL := /bin/zsh
API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: help install backend-dev frontend-dev mcp-dev mcp-stdio crewai-install temporal-worker temporal-up temporal-schema temporal-down temporal-status resilience-certify resilience-report identity-validate release-evaluate release-report db-up db-down observability-up observability-down migrate test lint typecheck check validate-config platform-up platform-down platform-status platform-logs platform-clean seed-synthetic verify-data verify-platform backup-databases restore-databases

help:
	@printf '%s\n' 'Targets: platform-up platform-down platform-status platform-logs platform-clean validate-config migrate seed-synthetic verify-data verify-platform backup-databases restore-databases temporal-up temporal-schema temporal-status temporal-worker resilience-certify resilience-report identity-validate release-evaluate release-report check'

install:
	python3.12 -m venv $(API_DIR)/.venv
	$(API_DIR)/.venv/bin/pip install -e '$(API_DIR)[dev]'
	$(API_DIR)/.venv/bin/pip install -e apps/crewai_client
	cd $(WEB_DIR) && npm install

backend-dev:
	cd $(API_DIR) && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd $(WEB_DIR) && npm run dev

mcp-dev:
	PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python -m apps.mcp_server.server --transport streamable-http

mcp-stdio:
	PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python -m apps.mcp_server.server --transport stdio

crewai-install:
	$(API_DIR)/.venv/bin/pip install -e apps/crewai_client

temporal-worker:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/run_temporal_worker.py

temporal-up:
	docker compose -f infra/docker-compose.yml --profile temporal up -d temporal-postgresql temporal-schema-init temporal temporal-namespace-init temporal-ui temporal-worker

temporal-schema:
	docker compose -f infra/docker-compose.yml run --rm temporal-schema-init

temporal-down:
	docker compose -f infra/docker-compose.yml --profile temporal stop temporal-ui temporal-namespace-init temporal temporal-schema-init temporal-worker temporal-postgresql

temporal-status:
	curl -sS http://127.0.0.1:8233/api/v1/namespaces/oncoagent | python3 -m json.tool

resilience-certify:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/resilience_certify.py $(if $(SCENARIO),--scenario $(SCENARIO),)

resilience-report:
	@ls -t evaluation_outputs/resilience/*.md 2>/dev/null | head -1 || true

identity-validate:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/validate_phase6a_identity.py

release-evaluate:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/release_evaluate.py $(if $(CANDIDATE),--candidate $(CANDIDATE),)

release-report:
	@ls -t evaluation_outputs/release/*.md 2>/dev/null | head -1 || true

db-up:
	docker compose -f infra/docker-compose.yml up -d

db-down:
	docker compose -f infra/docker-compose.yml down

observability-up:
	docker compose -f infra/docker-compose.yml --profile observability up -d otel-collector prometheus tempo grafana

observability-down:
	docker compose -f infra/docker-compose.yml --profile observability stop otel-collector prometheus tempo grafana

migrate:
	cd $(API_DIR) && .venv/bin/alembic upgrade head

validate-config:
	PYTHONPATH=$(API_DIR) python3 scripts/validate_config.py --service api

platform-up:
	docker compose -f infra/docker-compose.yml --profile full up -d --build

platform-down:
	docker compose -f infra/docker-compose.yml --profile full down

platform-status:
	docker compose -f infra/docker-compose.yml --profile full ps

platform-logs:
	docker compose -f infra/docker-compose.yml --profile full logs --tail=$${TAIL:-200}

platform-clean:
	@if [ "$${ALLOW_DESTRUCTIVE_CLEAN:-0}" = "1" ]; then docker compose -f infra/docker-compose.yml --profile full down --volumes; else echo 'Refusing to delete persistent volumes. Set ALLOW_DESTRUCTIVE_CLEAN=1 explicitly.'; docker compose -f infra/docker-compose.yml --profile full down; fi

seed-synthetic:
	PYTHONPATH=$(API_DIR) python3 scripts/seed_synthetic.py

verify-data:
	PYTHONPATH=$(API_DIR) python3 scripts/verify_data.py --dataset-name "$${SYNTHEA_DATASET_NAME:-synthea-eval-100}"

verify-platform:
	PYTHONPATH=$(API_DIR) python3 scripts/verify_platform.py

backup-databases:
	@out="$${BACKUP_DIR:-backups/$$(date +%Y%m%d-%H%M%S)}"; mkdir -p "$$out"; docker compose -f infra/docker-compose.yml exec -T postgres pg_dump -U "$${POSTGRES_USER:-oncoagent}" -d "$${POSTGRES_DB:-oncoagent}" > "$$out/application.sql"; if docker compose -f infra/docker-compose.yml ps -q temporal-postgresql | grep -q .; then docker compose -f infra/docker-compose.yml exec -T temporal-postgresql pg_dump -U temporal -d temporal > "$$out/temporal.sql"; fi; echo "database backups written under $$out (ignored by Git)"

restore-databases:
	@if [ "$${CONFIRM_RESTORE:-}" != "YES" ]; then echo 'Refusing restore. Set CONFIRM_RESTORE=YES and BACKUP_DIR explicitly.'; exit 2; fi; test -n "$${BACKUP_DIR:-}"; test -f "$${BACKUP_DIR}/application.sql"; docker compose -f infra/docker-compose.yml exec -T postgres psql -U "$${POSTGRES_USER:-oncoagent}" -d "$${POSTGRES_DB:-oncoagent}" < "$${BACKUP_DIR}/application.sql"; if [ -f "$${BACKUP_DIR}/temporal.sql" ] && docker compose -f infra/docker-compose.yml ps -q temporal-postgresql | grep -q .; then docker compose -f infra/docker-compose.yml exec -T temporal-postgresql psql -U temporal -d temporal < "$${BACKUP_DIR}/temporal.sql"; fi

test:
	cd $(API_DIR) && .venv/bin/pytest

lint:
	cd $(API_DIR) && .venv/bin/ruff check app tests
	cd $(WEB_DIR) && npm run lint

typecheck:
	cd $(API_DIR) && .venv/bin/mypy app
	cd $(WEB_DIR) && npm run typecheck

check: lint typecheck test
	cd $(WEB_DIR) && npm run build
