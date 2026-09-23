"""Async SQLAlchemy engine and session management.

The API and the worker share this module. Each creates its own engine at
startup and disposes it at shutdown, so connections never leak between
processes.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from legacydoc_core.settings import Settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> AsyncEngine:
    """Create the process-wide engine. Idempotent."""
    global _engine, _session_factory

    if _engine is not None:
        return _engine

    kwargs: dict = {
        "echo": False,
        "pool_pre_ping": True,
        "future": True,
    }

    # SQLite does not accept the Postgres pool parameters.
    if settings.database_url.startswith("postgresql"):
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow

    _engine = create_async_engine(settings.database_url, **kwargs)

    if settings.database_url.startswith("sqlite"):
        _enforce_sqlite_foreign_keys(_engine)

    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        autoflush=False,
    )
    return _engine


def _enforce_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """Liga a checagem de chave estrangeira em toda conexao SQLite.

    O SQLite aceita a declaracao e a ignora por padrao, entao `ON DELETE
    CASCADE` e `SET NULL` nao acontecem. Em desenvolvimento isso e pior que
    inutil: esconde defeito que so aparece em producao, onde o Postgres aplica.
    """
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _ligar(conexao, _registro):  # pragma: no cover - callback do driver
        cursor = conexao.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def dispose_engine() -> None:
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("init_engine() precisa ser chamado antes de abrir sessoes.")
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Transactional session: commits on success, rolls back on error, always closes."""
    factory = get_session_factory()
    session = factory()

    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency."""
    async with session_scope() as session:
        yield session
