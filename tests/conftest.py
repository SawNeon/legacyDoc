"""Fixtures da suite.

Os testes rodam em SQLite via aiosqlite para nao exigir container. A ressalva
importante: SQLite nao tem `FOR UPDATE SKIP LOCKED`, entao o caminho real de
concorrencia da fila em producao nao e exercido aqui - `test_queue.py` cobre o
fallback otimista e documenta a diferenca.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "chave-de-teste-com-mais-de-32-caracteres-ok")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MIN_PASSWORD_LENGTH", "10")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from legacydoc_core import db as db_module  # noqa: E402
from legacydoc_core.models import Base, User  # noqa: E402
from legacydoc_core.security import hash_password  # noqa: E402
from legacydoc_core.settings import Settings  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest.fixture
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def engine():
    # StaticPool mantem o mesmo :memory: entre conexoes da mesma sessao.
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    # The API and worker resolve sessions through the module globals.
    db_module._engine = engine
    db_module._session_factory = factory

    return factory


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    record = User(
        email=f"dev-{uuid.uuid4().hex[:8]}@exemplo.com",
        password_hash=hash_password("senha-bem-longa-123"),
        plan_tier="free",
    )
    session.add(record)
    await session.commit()

    return record


@pytest_asyncio.fixture
async def pro_user(session: AsyncSession) -> User:
    record = User(
        email=f"pro-{uuid.uuid4().hex[:8]}@exemplo.com",
        password_hash=hash_password("senha-bem-longa-123"),
        plan_tier="pro",
    )
    session.add(record)
    await session.commit()

    return record


@pytest_asyncio.fixture
async def client(session_factory, settings) -> AsyncIterator[AsyncClient]:
    from legacydoc_api.main import create_app

    app = create_app(settings)

    # Lifespan would create a real Postgres engine; tests inject SQLite.
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"user-{uuid.uuid4().hex[:8]}@exemplo.com"

    response = await client.post(
        "/v1/auth/register",
        json={"email": email, "password": "senha-bem-longa-123"},
    )
    assert response.status_code == 201, response.text

    return {"Authorization": f"Bearer {response.json()['access_token']}"}
