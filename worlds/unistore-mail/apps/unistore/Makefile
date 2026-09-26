# Run from worlds/unistore-mail/apps/unistore.
COMPOSE := docker compose --env-file .env -f compose.yaml --project-name world-unistore

.PHONY: pull up down build snapshot reset

ensure-env:
	python3 ../../../../scripts/common/runtime-env/ensure.py --world unistore-mail

pull: ensure-env
	$(COMPOSE) pull

up: ensure-env
	$(COMPOSE) up -d --wait --wait-timeout 180

down:
	$(COMPOSE) down

build: pull up
	./scripts/restore.sh

snapshot:
	./scripts/dump.sh

reset:
	./scripts/restore.sh
