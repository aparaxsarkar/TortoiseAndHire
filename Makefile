.PHONY: install lint format typecheck imports test test-cov up down run migrate revision seed ingest docker-build clean

install:
	pip install -e ".[dev]"

lint:
	ruff check app tests scripts

format:
	ruff format app tests scripts

typecheck:
	mypy

imports:
	lint-imports

test:
	pytest

test-cov:
	pytest --cov --cov-report=term-missing

up:
	docker compose up -d postgres

down:
	docker compose down

run:
	uvicorn app.main:app --reload

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

seed:
	python -m scripts.seed_sources

ingest:
	python -m scripts.run_ingestion $(s)

docker-build:
	docker build -f docker/Dockerfile -t tortoiseandhire:local .

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
