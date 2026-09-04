SHELL := /bin/zsh
API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: help install backend-dev frontend-dev mcp-dev mcp-stdio crewai-install temporal-worker temporal-up temporal-schema temporal-down temporal-status resilience-certify resilience-report identity-validate release-evaluate release-report performance-smoke performance-run performance-report reliability-verify security-scan security-tools-install secret-scan dependency-scan privacy-scan audit-integrity-verify security-verify retention-dry-run db-up db-down observability-up observability-down migrate demo-up demo-down demo-status demo-check demo-prepare demo-populate demo-populate-research demo-populate-operations demo-guided demo-auto demo-record demo-report demo-reset load-check load-smoke load-baseline load-sustained load-burst load-mcp load-langgraph load-crewai load-governance load-retry load-recovery load-cancel load-overload load-slo load-all load-status load-report load-grafana-capture test lint typecheck check validate-config platform-up platform-down platform-status platform-logs platform-clean seed-synthetic verify-data verify-platform backup-databases restore-databases validation-create validation-down artifacts-clean-dry-run artifacts-clean ollama-check ollama-prepare

help:
	@printf '%s\n' 'Targets: platform-up platform-down platform-status platform-logs platform-clean validate-config migrate seed-synthetic verify-data verify-platform backup-databases restore-databases validation-create validation-down artifacts-clean-dry-run artifacts-clean ollama-check ollama-prepare temporal-up temporal-schema temporal-status temporal-worker resilience-certify resilience-report identity-validate release-evaluate release-report performance-smoke performance-run performance-report reliability-verify security-scan secret-scan dependency-scan privacy-scan audit-integrity-verify retention-dry-run security-verify check'

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
	$(API_DIR)/.venv/bin/pip install -e 'apps/crewai_client[crewai]'

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

performance-smoke:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/performance_runner.py --profile api-read-light

performance-run:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/performance_runner.py --profile "$(if $(PROFILE),$(PROFILE),api-read-concurrent)"

performance-report:
	@ls -t evaluation_outputs/performance/*.md 2>/dev/null | head -1 || true

reliability-verify:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/performance_runner.py --profile retry-recovery

security-tools-install:
	$(API_DIR)/.venv/bin/pip install -e '$(API_DIR)[dev]'
	docker pull aquasec/trivy:0.61.0
	cd $(WEB_DIR) && npm install --package-lock-only --ignore-scripts

security-scan:
	TRIVY_COMMAND="docker run --rm -v $$(pwd):/work:ro -w /work aquasec/trivy:0.61.0" PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/security_scan.py --check all --strict

secret-scan:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/security_scan.py --check secrets

dependency-scan:
	TRIVY_COMMAND="docker run --rm -v $$(pwd):/work:ro -w /work aquasec/trivy:0.61.0" PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/security_scan.py --check dependencies --strict

privacy-scan:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/security_scan.py --check privacy

audit-integrity-verify:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/audit_integrity_verify.py

retention-dry-run:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/security_retention.py

security-verify:
	@set +e; rc=0; for target in secret-scan privacy-scan dependency-scan audit-integrity-verify retention-dry-run; do $(MAKE) --no-print-directory "$$target"; code=$$?; if [ $$code -gt $$rc ]; then rc=$$code; fi; done; exit $$rc

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

demo-prepare: migrate verify-data
	@echo 'Demo prerequisites verified: existing bounded synthetic dataset and schema are ready.'
	@echo 'No records are inserted or deleted by this target; use seed-synthetic only when a Synthea archive is explicitly provided.'

demo-up:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/prepare_demo_env.py
	/Applications/Docker.app/Contents/Resources/bin/docker compose -p oncoagent --env-file .env.demo -f infra/docker-compose.yml --profile full up -d --build

demo-down:
	/Applications/Docker.app/Contents/Resources/bin/docker compose -p oncoagent --env-file .env.demo -f infra/docker-compose.yml --profile full down

demo-status:
	PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python scripts/demo_orchestrator.py status

demo-check:
	PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python scripts/demo_orchestrator.py check

demo-populate:
	@if [ -n "$${DEMO_ID:-}" ]; then PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python scripts/demo_orchestrator.py populate --demo-id "$${DEMO_ID}"; else PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python scripts/demo_orchestrator.py populate; fi

demo-populate-research:
	@if [ -n "$${DEMO_ID:-}" ]; then PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python scripts/demo_orchestrator.py research --demo-id "$${DEMO_ID}"; else PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python scripts/demo_orchestrator.py research; fi

demo-populate-operations:
	@if [ -n "$${DEMO_ID:-}" ]; then PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python scripts/demo_orchestrator.py operations --demo-id "$${DEMO_ID}"; else PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python scripts/demo_orchestrator.py operations; fi

demo-guided:
	@echo 'Open http://127.0.0.1:3000/demo after demo-populate completes.'

demo-auto: demo-check demo-prepare demo-populate

demo-record:
	@echo 'Browser recording requires the Playwright runner; no records are changed by this target.'

demo-report:
	PYTHONPATH=apps/api $(API_DIR)/.venv/bin/python scripts/demo_orchestrator.py report

demo-reset:
	@if [ -z "$${DEMO_ID:-}" ]; then echo 'Set DEMO_ID=client-demo-...'; exit 2; fi
	@if [ "$${CONFIRM_DEMO_RESET:-}" = "YES" ]; then \
		PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/demo_reset.py --demo-id "$${DEMO_ID}" --confirm; \
	else \
		PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/demo_reset.py --demo-id "$${DEMO_ID}"; \
	fi

load-check:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py check

load-smoke:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py smoke

load-baseline:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py baseline

load-sustained:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py sustained

load-burst:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py burst

load-mcp:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py mcp

load-langgraph:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py langgraph

load-crewai:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py crewai

load-governance:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py governance

load-retry:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py retry

load-recovery:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py recovery

load-cancel:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py cancel

load-overload:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py overload

load-slo:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py slo

load-all:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py all

load-status:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py status

load-report:
	PYTHONPATH=apps/api:apps:loadtests $(API_DIR)/.venv/bin/python loadtests/run.py report

load-grafana-capture:
	cd $(WEB_DIR) && npm run load:grafana-capture

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

validation-create:
	CONFIRM_VALIDATION_CREATE=$${CONFIRM_VALIDATION_CREATE:-} PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/validation_database.py --env-file "$${VALIDATION_SOURCE_ENV_FILE:-.env.demo}"

validation-down:
	@if [ -z "$${VALIDATION_PROJECT:-}" ]; then echo 'Set VALIDATION_PROJECT to the exact validation Compose project; no volume removal is performed.'; exit 2; fi
	docker compose -p "$${VALIDATION_PROJECT}" --env-file "$${VALIDATION_SOURCE_ENV_FILE:-.env.demo}" -f infra/docker-compose.yml stop postgres

artifacts-clean-dry-run:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/cleanup_artifacts.py --dry-run

artifacts-clean:
	@if [ "$${CONFIRM_ARTIFACT_CLEAN:-}" != "YES" ]; then echo 'Refusing artifact cleanup. Set CONFIRM_ARTIFACT_CLEAN=YES explicitly.'; exit 2; fi
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/cleanup_artifacts.py --apply

ollama-check:
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/ollama_check.py

ollama-prepare:
	@if [ "$${CONFIRM_OLLAMA_SETUP:-}" != "YES" ]; then echo 'Refusing Ollama setup. Set CONFIRM_OLLAMA_SETUP=YES explicitly.'; exit 2; fi
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/ollama_check.py --prepare

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
