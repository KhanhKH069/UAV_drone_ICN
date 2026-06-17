# ============================================================
# UAV_drone_ICN — Makefile
# Inspired by Vexa's Makefile (make all / make up / make logs)
# ============================================================

.PHONY: all env build up down logs health download-models clean local-build local-up

## Full setup: env → build → up (run once on fresh server)
all: env build up
	@echo ""
	@echo "🚁 UAV_drone_ICN Edge Server is running!"
	@echo "   API Gateway:  http://localhost:8056"
	@echo "   Docs:         http://localhost:8056/docs"
	@echo "   WebSocket:    ws://localhost:8765"
	@echo ""

## Create .env from example (skips if already exists)
env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✅ .env created from .env.example"; \
		echo "⚠️  Edit .env with your server IP and Teams credentials!"; \
	else \
		echo "ℹ️  .env already exists, skipping."; \
	fi

## Build all Docker images
build:
	docker compose build --parallel

## Start all services in detached mode
up:
	docker compose up -d
	@echo "⏳ Waiting for services to be healthy..."
	@sleep 5
	@$(MAKE) health

## Local-specific: build and up using docker-compose.local.yml (Disable Agent/Vision)
local-build:
	docker compose -f docker-compose.local.yml build --parallel

local-up:
	docker compose -f docker-compose.local.yml up -d
	@echo "⏳ Waiting for local services to be healthy..."
	@sleep 5
	@$(MAKE) health



## Stop all services
down:
	docker compose down

## Tail logs (all services or specific: make logs s=api-gateway)
logs:
ifdef s
	docker compose logs -f $(s)
else
	docker compose logs -f
endif

## Show container status
ps:
	docker compose ps

## Health check all services
health:
	@echo "Checking service health..."
	@curl -sf http://localhost:8056/health && echo "✅ api-gateway" || echo "❌ api-gateway"
	@curl -sf http://localhost:8001/health && echo "✅ whisperlive" || echo "❌ whisperlive"
	@curl -sf http://localhost:8002/health && echo "✅ translation" || echo "❌ translation"
	@curl -sf http://localhost:8005/health && echo "✅ agent" || echo "❌ agent"

## Download AI models (run BEFORE first `make up`)
download-models:
	@echo "📦 Downloading AI models..."
	bash scripts/download_models.sh

## Pull Ollama LLM model (after services are up)
pull-llm:
	docker compose exec ollama ollama pull llama3:8b
	@echo "✅ Llama 3 8B downloaded"

## Hard reset: remove containers + volumes (⚠️ deletes all data)
clean:
	docker compose down -v --remove-orphans
	@echo "🗑️  All containers and volumes removed"

## Restart a specific service: make restart s=translation-service
restart:
ifdef s
	docker compose restart $(s)
else
	docker compose restart
endif
