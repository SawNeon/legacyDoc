"""Entrypoint do worker: `python -m legacydoc_worker`."""

from __future__ import annotations

import asyncio
import logging

from legacydoc_core.settings import get_settings

from legacydoc_worker.runner import Worker


def main() -> None:
    settings = get_settings()

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    asyncio.run(Worker(settings).run())


if __name__ == "__main__":
    main()
