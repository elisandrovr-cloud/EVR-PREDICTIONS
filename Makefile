.PHONY: up down logs build test test-backend typecheck seed clean

up: ## Arranca toda la plataforma
	docker compose up -d --build

down: ## Detiene todo
	docker compose down

logs: ## Logs en vivo
	docker compose logs -f --tail=100

build: ## Reconstruye imágenes
	docker compose build

test: test-backend typecheck ## Ejecuta todas las pruebas

test-backend:
	cd backend && python -m pytest

typecheck:
	cd frontend && npm run typecheck

seed: ## Fuerza el bootstrap de datos (equipos + cartelera + stats)
	docker compose exec backend python -c "from app.workers.tasks import bootstrap_reference_data; bootstrap_reference_data.delay()"

clean: ## Elimina contenedores y volúmenes (¡borra la base de datos!)
	docker compose down -v
