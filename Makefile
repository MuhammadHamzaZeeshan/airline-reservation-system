.PHONY: up up-full down clean ps logs init-db init-db-ha seed health test test-unit test-race test-summary load load-heavy spike soak storm chaos verify-distribution verify-inventory wait frontend-dev

SCALE ?= 0.01
LITE = docker compose -f docker-compose.lite.yml
FULL = docker compose -f docker-compose.yml

.env:
	cp .env.example .env

up: .env
	$(LITE) up -d --build
	@$(MAKE) --no-print-directory wait

up-full: .env
	MONGO_RS_MEMBERS=mongo:27017,mongo2:27017,mongo3:27017 COMPOSE_FILE=docker-compose.yml $(FULL) up -d --build

wait:
	@echo "Waiting for the edge (nginx) to become healthy..."
	@for i in $$(seq 1 120); do \
	  s=$$(docker inspect -f '{{.State.Health.Status}}' ars-nginx 2>/dev/null); \
	  [ "$$s" = "healthy" ] && echo "stack healthy" && exit 0; sleep 3; done; \
	  echo "timeout waiting for stack"; $(LITE) ps; exit 1

init-db:
	./scripts/init_db.sh

init-db-ha:
	HA=1 COMPOSE_FILE=docker-compose.yml ./scripts/init_db.sh
	sed -i 's/^USE_REPLICAS=.*/USE_REPLICAS=true/' .env
	COMPOSE_FILE=docker-compose.yml docker compose up -d api1 api2 api3

# SCALE=1 -> 50M flights (hours; use a 16 vCPU / 32 GB machine). Default SCALE=0.01 -> 500k flights (minutes).
seed:
	docker compose exec -T api1 python -m seed.seed --scale $(SCALE) --force

health:
	@curl -s http://127.0.0.1:$${HTTP_PORT:-8080}/health | python3 -m json.tool

down:
	$(LITE) down

clean:
	COMPOSE_FILE=docker-compose.yml docker compose down -v --remove-orphans

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=100

test-unit:
	docker compose exec -T api1 python -m pytest app/tests -q

test-race:
	docker compose exec -T -e API_URL=http://nginx:80 -e PG_TEST_HOST=coordinator api1 python -m pytest loadtest/race_tests -q

test: test-unit test-race

test-summary:
	./scripts/test_summary.sh

load:
	docker exec ars-k6 k6 run /scripts/baseline.js
load-heavy:
	docker exec ars-k6 k6 run /scripts/heavy.js
spike:
	docker exec ars-k6 k6 run /scripts/spike.js
soak:
	docker exec ars-k6 k6 run /scripts/soak.js
storm:
	docker exec ars-k6 k6 run /scripts/booking_storm.js
	$(MAKE) --no-print-directory verify-inventory

chaos:
	./chaos/run_all.sh

verify-distribution:
	docker compose exec -T coordinator psql -U $${POSTGRES_USER:-ars} -d $${POSTGRES_DB:-ars} -f - < sql/verify_distribution.sql

verify-inventory:
	docker compose exec -T coordinator psql -U $${POSTGRES_USER:-ars} -d $${POSTGRES_DB:-ars} -f - < sql/verify_inventory.sql

frontend-dev:
	cd frontend && npm install && npm run dev
