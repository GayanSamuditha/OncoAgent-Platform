SHELL := /bin/zsh
API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: help install backend-dev frontend-dev mcp-dev mcp-stdio crewai-install temporal-worker temporal-up temporal-schema temporal-down temporal-status db-up db-down observability-up observability-down migrate test lint typecheck check

help:
	@printf '%s\n' 'Targets: temporal-up temporal-schema temporal-status temporal-worker temporal-down db-up db-down migrate check'

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
	docker compose -f infra/docker-compose.yml up -d temporal-postgresql temporal-schema-init temporal temporal-namespace-init temporal-ui

temporal-schema:
	docker compose -f infra/docker-compose.yml run --rm temporal-schema-init

temporal-down:
	docker compose -f infra/docker-compose.yml stop temporal-ui temporal-namespace-init temporal temporal-schema-init temporal-postgresql

temporal-status:
	curl -sS http://127.0.0.1:8233/api/v1/namespaces/oncoagent | python3 -m json.tool

db-up:
	docker compose -f infra/docker-compose.yml up -d

db-down:
	docker compose -f infra/docker-compose.yml down

observability-up:
	docker compose -f infra/docker-compose.yml up -d otel-collector prometheus tempo grafana

observability-down:
	docker compose -f infra/docker-compose.yml stop otel-collector prometheus tempo grafana

migrate:
	cd $(API_DIR) && .venv/bin/alembic upgrade head

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
