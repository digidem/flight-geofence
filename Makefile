.PHONY: up public down logs test lint check sync poll backup fix-permissions bump-version dev

# Canonical version source: app/main.py line with APP_VERSION = "X.Y.Z"
VERSION_FILES_BARE = Dockerfile app/main.py LINKS_REPORT.txt
VERSION_FILES_VPREFIX = README.md docs/VALIDATION.md docs/AUDIT.md

bump-version:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make bump-version VERSION=0.5.0"; exit 1; fi
	@OLD=$$(grep -oP '(?<=APP_VERSION = ")[^"]+' app/main.py); \
	for f in $(VERSION_FILES_BARE); do \
		sed -i "s/$$OLD/$(VERSION)/g" "$$f"; \
	done; \
	for f in $(VERSION_FILES_VPREFIX); do \
		sed -i "s/v$$OLD/v$(VERSION)/g" "$$f"; \
	done
	@echo "Version bumped to $(VERSION)"
	@echo "  Bare:    $(VERSION_FILES_BARE)"
	@echo "  v-pref:  $(VERSION_FILES_VPREFIX)"
	@echo "Review changes, commit, then trigger the release workflow."

up:
	docker compose up --build -d

public:
	docker compose --profile public up --build -d

down:
	docker compose down

logs:
	docker compose logs -f flight-monitor

dev:
	uv run uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload

test:
	uv run python -m pytest

lint:
	uv run python -m ruff check app tests

check:
	uv run python -m compileall -q app tests
	uv run python -m pytest

sync:
	docker compose exec flight-monitor python -m app.cli sync

poll:
	docker compose exec flight-monitor python -m app.cli poll

backup:
	./scripts/backup.sh

fix-permissions:
	docker compose --profile maintenance run --rm permissions
