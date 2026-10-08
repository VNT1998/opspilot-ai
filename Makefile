.PHONY: setup test eval dev-backend dev-frontend docker-up clean

setup:
	@echo "Setting up backend with uv..."
	cd backend && uv sync --all-groups
	@echo "Setting up frontend with npm..."
	cd frontend && npm install

test:
	@echo "Running backend test suite..."
	cd backend && uv run pytest -v

eval:
	@echo "Running 50-case benchmark evaluation suite..."
	cd backend && uv run python ../evals/scripts/run_evals.py

dev-backend:
	@echo "Starting FastAPI backend server on http://localhost:8000..."
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend:
	@echo "Starting Vite frontend dev server on http://localhost:5173..."
	cd frontend && npm run dev

docker-up:
	@echo "Starting full Docker Compose stack (API, Frontend, Postgres, Redis)..."
	docker compose up --build -d

docker-down:
	docker compose down

clean:
	rm -rf backend/.pytest_cache backend/__pycache__ backend/opspilot.db
	rm -rf frontend/dist frontend/node_modules/.vite
