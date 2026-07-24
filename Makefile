.PHONY: up public down logs test lint check sync poll backup fix-permissions

up:
	docker compose up --build -d

public:
	docker compose --profile public up --build -d

down:
	docker compose down

logs:
	docker compose logs -f flight-monitor

test:
	python -m pytest

lint:
	python -m ruff check app tests

check:
	python -m compileall -q app tests
	python -m pytest

sync:
	docker compose exec flight-monitor python -m app.cli sync

poll:
	docker compose exec flight-monitor python -m app.cli poll

backup:
	./scripts/backup.sh

fix-permissions:
	docker compose --profile maintenance run --rm permissions
