# Convenience targets. Run `make help` for the list.
.DEFAULT_GOAL := help
.PHONY: help install backend frontend test lint build sample docker up down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (dev) and frontend dependencies
	cd backend && pip install -r requirements-dev.txt
	cd frontend && npm install

backend: ## Run the backend dev server
	cd backend && uvicorn app.main:app --reload --port 8000

frontend: ## Run the frontend dev server
	cd frontend && npm run dev

test: ## Run backend tests
	cd backend && pytest

lint: ## Lint + type-check backend (ruff, mypy) and type-check frontend
	cd backend && ruff check app tests && mypy app --ignore-missing-imports
	cd frontend && npm run build

build: ## Production build of the frontend
	cd frontend && npm run build

sample: ## Generate the synthetic sample video
	python scripts/generate_sample_video.py sample_data/sample_exam_hall.mp4

docker: ## Build docker images
	docker compose build

up: ## Start the full stack (docker compose)
	docker compose up --build

down: ## Stop the stack
	docker compose down

clean: ## Remove generated artefacts (keeps sample_data/outputs)
	rm -rf storage/videos/* storage/clips/* storage/heatmaps/* \
		storage/thumbnails/* storage/reports/* data/app.db
	rm -rf frontend/dist backend/.pytest_cache
