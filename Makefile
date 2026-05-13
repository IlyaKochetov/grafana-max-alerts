.PHONY: dev test lint format typecheck build up down

dev:
	uv run uvicorn app.main:app --reload --port 8000

test:
	uv run pytest

lint:
	uv run ruff check app/ tests/

format:
	uv run ruff format app/ tests/

typecheck:
	uv run mypy app/

build:
	docker compose build

up:
	docker compose up -d --build

down:
	docker compose down
