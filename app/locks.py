from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import env_settings


@contextmanager
def exclusive_job_lock(name: str) -> Iterator[bool]:
    """Acquire a non-blocking process-wide lock stored beside the SQLite DB.

    The in-memory asyncio locks prevent overlap inside one server process. This
    file lock also prevents a `docker compose exec ... app.cli` command from
    overlapping the scheduler in another process.
    """

    safe_name = "".join(character for character in name if character.isalnum() or character in "-_")
    if not safe_name:
        raise ValueError("Lock name must contain an alphanumeric character")
    lock_path = Path(env_settings().database_path).parent / f".{safe_name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
