.PHONY: install lint format typecheck imports test test-cov up down run clean

install:
	pip install -e ".[dev]"

lint:
	ruff check app tests

format:
	ruff format app tests

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

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
