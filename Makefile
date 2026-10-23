.PHONY: up down migrate test lint backend-install miniapp-install

up:
	docker compose -f docker-compose.dev.yml up -d postgres redis minio

down:
	docker compose -f docker-compose.dev.yml down

backend-install:
	cd backend && pip install -e ".[dev]"

miniapp-install:
	cd miniapp && npm install

migrate:
	cd backend && alembic upgrade head

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check . && mypy app/domain app/core
	cd miniapp && npm run lint

dev-api:
	cd backend && uvicorn app.main:app --reload --port 8000

seed:
	cd backend && python -m scripts.seed
