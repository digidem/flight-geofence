.PHONY: up public down logs test lint check a11y sync poll backup fix-permissions bump-version dev

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
	DATABASE_PATH=$${DATABASE_PATH:-data/runtime/flight_alerts.db} \
	DOWNLOAD_DIR=$${DOWNLOAD_DIR:-data/downloads} \
	uv run uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload

test:
	uv run python -m pytest

lint:
	uv run python -m ruff check app tests

check:
	uv run python -m compileall -q app tests
	uv run python -m pytest
	@echo "# optional: npx lighthouse http://127.0.0.1:8081 --chrome-flags=\"--headless\" (requires axe-core/lighthouse dev deps, see 'make a11y' notes)"

a11y:
	uv run python -m pytest -q
	@if npx --yes axe-core --version >/dev/null 2>&1; then \
		echo "axe-core found — running axe checks (add real CLI wiring as needed)"; \
		npx --yes axe-core --version; \
	else \
		echo "skip: axe-core not installed — run 'npm i -D axe-core lighthouse' (requires approval)"; \
	fi
	@if npx --yes lighthouse --version >/dev/null 2>&1; then \
		echo "lighthouse found — to run: npx lighthouse http://127.0.0.1:8081 --chrome-flags=\"--headless\" --output=json --output-path=./lighthouse.json"; \
		npx --yes lighthouse --version; \
	else \
		echo "skip: lighthouse not installed — run 'npm i -D axe-core lighthouse' (requires approval)"; \
	fi
	@echo "a11y: optional dev deps axe-core/lighthouse remain dependency-free unless approved (npm i -D axe-core lighthouse)"

sync:
	docker compose exec flight-monitor python -m app.cli sync

poll:
	docker compose exec flight-monitor python -m app.cli poll

backup:
	./scripts/backup.sh

fix-permissions:
	docker compose --profile maintenance run --rm permissions
