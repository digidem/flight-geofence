import atexit
import os
import shutil
import tempfile
from pathlib import Path

os.environ.setdefault("ADMIN_PASSWORD", "correct-horse-battery-staple")
os.environ.setdefault("APP_SECRET_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "false")
os.environ.setdefault("BOUNDARY_SYNC_ENABLED", "false")
os.environ.setdefault("SCHEDULER_INITIAL_DELAY_SECONDS", "9999")
os.environ.setdefault("TRUSTED_HOSTS", "testserver,localhost,127.0.0.1")
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="flight-geofence-tests-"))
atexit.register(lambda: shutil.rmtree(_TEST_ROOT, ignore_errors=True))
os.environ.setdefault("DATABASE_PATH", str(_TEST_ROOT / "test.db"))
os.environ.setdefault("DOWNLOAD_DIR", str(_TEST_ROOT / "downloads"))

import pytest

from app.config import env_settings
from app.database import db, init_db


@pytest.fixture(autouse=True)
def clean_database():
    env_settings.cache_clear()
    init_db()
    with db() as conn:
        for table in (
            "app_settings",
            "areas",
            "query_regions",
            "dataset_syncs",
            "poll_runs",
            "aircraft_state",
            "events",
            "provider_requests",
        ):
            conn.execute(f"DELETE FROM {table}")
    yield
