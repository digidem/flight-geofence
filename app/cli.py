import argparse
import asyncio

from .boundary_sync import sync_boundaries
from .database import init_db
from .main import run_coverage_cycle


async def main_async(command: str) -> None:
    init_db()
    if command == "sync":
        print(await sync_boundaries())
    elif command == "poll":
        print(await run_coverage_cycle())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("sync", "poll"))
    args = parser.parse_args()
    asyncio.run(main_async(args.command))


if __name__ == "__main__":
    main()
