"""Development entrypoint: `python -m legacydoc_api`.

In production the service runs under uvicorn with the process managed by
systemd or Docker, never through this module.
"""

from __future__ import annotations

import uvicorn
from legacydoc_core.settings import get_settings


def main() -> None:
    settings = get_settings()

    uvicorn.run(
        "legacydoc_api.main:get_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=not settings.is_production,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
