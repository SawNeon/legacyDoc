"""Alembic environment.

The URL always comes from DATABASE_URL, never from alembic.ini, so there is no
second copy of the credentials in the repository.
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

    if not url:
        raise RuntimeError("DATABASE_URL nao definida; o Alembic nao sabe onde migrar.")

    return url


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
