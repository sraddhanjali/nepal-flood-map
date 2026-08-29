.PHONY: help build up down logs shell test clean

help:
	@echo "Nepal CEMS Rapid Activation Map - Development commands"
	@echo "Usage:"
	@echo "  make build          Build Docker images"
	@echo "  make up             Start services (API + dev server)"
	@echo "  make up-prod        Start only API in production mode"
	@echo "  make down           Stop all services"
	@echo "  make logs           Tail service logs"
	@echo "  make shell          Open shell in API container"
	@echo "  make test           Run API health check"
	@echo "  make clean          Remove containers and volumes"

build:
	docker-compose build

up:
	docker-compose --profile dev up -d
	@echo "✓ API running at http://localhost:8000"
	@echo "✓ Frontend dev server at http://localhost:5173"

up-prod:
	docker-compose up -d api

down:
	docker-compose down

logs:
	docker-compose logs -f

shell:
	docker-compose exec api /bin/bash

test:
	curl -f http://localhost:8000/health || echo "API not responding"

clean:
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf node_modules dist .vite
