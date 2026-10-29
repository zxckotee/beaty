.PHONY: up down migrate test lint backend-install

up:
	docker compose up -d postgres redis minio

down:
	docker compose down

backend-install:
	cd backend && pip install -e ".[dev]"

migrate:
	cd backend && alembic upgrade head

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check . && mypy app/domain app/core

dev-api:
	cd backend && uvicorn app.main:app --reload --port 8000

seed:
	cd backend && python -m scripts.seed
