.PHONY: setup db test lint run web build clean-db

setup:            ## Create venv and install dependencies
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
	cd frontend && npm install

db:               ## Start local PostgreSQL (needs Docker); also creates the test database
	docker compose up -d db
	@until docker compose exec -T db pg_isready -U tp -d tp_dev >/dev/null 2>&1; do sleep 1; done
	-docker compose exec -T db psql -U tp -d tp_dev -c "CREATE DATABASE tp_test"

test:             ## Backend tests (need TEST_DATABASE_URL or the default local database)
	.venv/bin/python -m pytest -q

lint:             ## Lint backend and type-check frontend
	.venv/bin/ruff check backend tools
	cd frontend && npm run typecheck

run:              ## Run API on :8000 (serves frontend/dist if built)
	.venv/bin/uvicorn --factory travel_planner.main:create_app --app-dir backend --reload --port 8000

web:              ## Run the frontend dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

build:            ## Build the frontend into frontend/dist
	cd frontend && npm run build
