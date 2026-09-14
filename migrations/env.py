"""Alembic environment.

The URL always comes from DATABASE_URL, never from alembic.ini, so there is no
second copy of the credentials in the repository.

It is read the same way the application reads it: an exported environment
variable first, then the project `.env`. Reading only the environment made
`alembic upgrade head` fail on a machine whose `.env` was correct, because the
API picked the value up from the file and the migration did not.
"""

from __future__ import annotations

import asyncio
import os

from alembic import context
from legacydoc_core.models import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")

    if url:
        return url

    # Only loaded when the variable is not exported, so rendering SQL in CI
    # keeps working without the other settings the application requires.
    from legacydoc_core.settings import get_settings

    try:
        return get_settings().database_url
    except Exception as exc:
        raise RuntimeError(
            "DATABASE_URL nao definida no ambiente nem no .env; o Alembic nao sabe onde migrar."
        ) from exc


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    engine = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
