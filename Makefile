SHELL := /bin/zsh
API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: install backend-dev frontend-dev db-up db-down migrate test lint typecheck check

install:
	python3.12 -m venv $(API_DIR)/.venv
	$(API_DIR)/.venv/bin/pip install -e '$(API_DIR)[dev]'
	cd $(WEB_DIR) && npm install

backend-dev:
	cd $(API_DIR) && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd $(WEB_DIR) && npm run dev

db-up:
	docker compose -f infra/docker-compose.yml up -d

db-down:
	docker compose -f infra/docker-compose.yml down

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
