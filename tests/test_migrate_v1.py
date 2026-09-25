"""Migration tests for v1 -> v2."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from legacydoc_cli.migrate_v1 import migrate_users, read_legacy_users
from legacydoc_core.errors import ValidationError
from legacydoc_core.models import User
from legacydoc_core.security import verify_password
from pwdlib import PasswordHash
from sqlalchemy import select

KNOWN_PASSWORD = "senha-do-usuario-123"


@pytest.fixture
def legacy_database(tmp_path: Path) -> Path:
    """Recreate the exact v1 schema, including its defects."""
    database_path = tmp_path / "legacydoc.db"
    connection = sqlite3.connect(database_path)

    connection.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    legacy_hash = PasswordHash.recommended().hash(KNOWN_PASSWORD)
    timestamp = datetime.now(UTC).isoformat()

    connection.executemany(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        [
            ("ana@empresa.com", legacy_hash, timestamp),
            ("bruno@empresa.com", legacy_hash, timestamp),
            ("email-invalido", legacy_hash, timestamp),
            ("carlos@empresa.com", "$2b$12$hashdebcryptqualquer", timestamp),
        ],
    )
    connection.commit()
    connection.close()

    return database_path


async def test_reads_every_legacy_user(legacy_database: Path):
    legacy_users = read_legacy_users(legacy_database)

    assert len(legacy_users) == 4
    assert legacy_users[0].email == "ana@empresa.com"


async def test_missing_file_reports_clear_error(tmp_path: Path):
    with pytest.raises(ValidationError, match="nao encontrado"):
        read_legacy_users(tmp_path / "does-not-exist.db")


async def test_file_without_users_table_is_rejected(tmp_path: Path):
    database_path = tmp_path / "other.db"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE something_else (id INTEGER)")
    connection.commit()
    connection.close()

    with pytest.raises(ValidationError, match="tabela `users`"):
        read_legacy_users(database_path)


async def test_dry_run_writes_nothing(legacy_database: Path, session_factory, session):
    report = await migrate_users(
        session, read_legacy_users(legacy_database), plan="free", apply_changes=False
    )

    assert len(report.migrated) == 2
    assert (await session.execute(select(User))).scalars().all() == []


async def test_migration_preserves_password(legacy_database: Path, session_factory, session):
    """Decides whether cutover forces a mass password reset."""
    await migrate_users(
        session, read_legacy_users(legacy_database), plan="free", apply_changes=True
    )

    ana = (await session.execute(select(User).where(User.email == "ana@empresa.com"))).scalar_one()

    assert verify_password(KNOWN_PASSWORD, ana.password_hash)
    assert not verify_password("senha-errada", ana.password_hash)


async def test_invalid_email_is_skipped(legacy_database: Path, session_factory, session):
    """Migrating it would create an account nobody could ever log into."""
    report = await migrate_users(
        session, read_legacy_users(legacy_database), plan="free", apply_changes=True
    )

    assert "email-invalido" in {email for email, _ in report.skipped}

    stored_emails = {email for (email,) in (await session.execute(select(User.email))).all()}
    assert "email-invalido" not in stored_emails


async def test_foreign_hash_scheme_is_skipped(legacy_database: Path, session_factory, session):
    report = await migrate_users(
        session, read_legacy_users(legacy_database), plan="free", apply_changes=True
    )

    reasons = dict(report.skipped)
    assert "carlos@empresa.com" in reasons
    assert "argon2" in reasons["carlos@empresa.com"]


async def test_migration_is_idempotent(legacy_database: Path, session_factory, session):
    legacy_users = read_legacy_users(legacy_database)

    first_run = await migrate_users(session, legacy_users, plan="free", apply_changes=True)
    second_run = await migrate_users(session, legacy_users, plan="free", apply_changes=True)

    assert len(first_run.migrated) == 2
    assert len(second_run.migrated) == 0
    assert len(second_run.already_present) == 2
    assert len((await session.execute(select(User))).scalars().all()) == 2


async def test_selected_plan_is_applied(legacy_database: Path, session_factory, session):
    await migrate_users(session, read_legacy_users(legacy_database), plan="pro", apply_changes=True)

    plans = dict((await session.execute(select(User.email, User.plan_tier))).all())

    assert plans["ana@empresa.com"] == "pro"


async def test_creation_date_is_preserved(legacy_database: Path, session_factory, session):
    await migrate_users(
        session, read_legacy_users(legacy_database), plan="free", apply_changes=True
    )

    ana = (await session.execute(select(User).where(User.email == "ana@empresa.com"))).scalar_one()

    assert ana.created_at.year == datetime.now(UTC).year


async def test_legacy_database_is_not_modified(legacy_database: Path, session_factory, session):
    """Opened read-only so v1 can stay live during the copy."""
    modified_before = legacy_database.stat().st_mtime_ns

    await migrate_users(
        session, read_legacy_users(legacy_database), plan="free", apply_changes=True
    )

    assert legacy_database.stat().st_mtime_ns == modified_before
