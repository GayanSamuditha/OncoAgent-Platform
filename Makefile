SHELL := /bin/zsh
API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: install backend-dev frontend-dev mcp-dev mcp-stdio crewai-install db-up db-down observability-up observability-down migrate test lint typecheck check

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
