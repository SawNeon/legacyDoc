"""One-way copy of v1 users from SQLite into the v2 Postgres database.

The two databases stay separate so both versions can run side by side during
the transition and the switch stays reversible. Re-running skips users that
already exist rather than duplicating them.

Passwords survive the move: both versions use `pwdlib.PasswordHash.recommended()`,
which produces argon2id in the same format, and the hash is copied verbatim.

Generated documents are not migrated because v1 stores no file owner, so there
is nobody to attribute them to.

    python -m legacydoc_cli.migrate_v1 --source path/to/legacydoc.db
    python -m legacydoc_cli.migrate_v1 --source path/to/legacydoc.db --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from legacydoc_core.db import dispose_engine, init_engine, session_scope
from legacydoc_core.errors import ValidationError
from legacydoc_core.models import User
from legacydoc_core.plans import PlanTier
from legacydoc_core.security import validate_email
from legacydoc_core.settings import Settings, get_settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_cli.console import Style, section

ARGON2_PREFIX = "$argon2"
DEFAULT_SOURCE = "legacyDoc/legacyDoc/legacydoc.db"


@dataclass(frozen=True)
class LegacyUser:
    id: int
    email: str
    password_hash: str
    created_at: str


@dataclass
class MigrationReport:
    migrated: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_read(self) -> int:
        return len(self.migrated) + len(self.already_present) + len(self.skipped)


def read_legacy_users(database_path: Path) -> list[LegacyUser]:
    """Read the v1 users read-only, so the old service can keep running."""
    if not database_path.is_file():
        raise ValidationError(f"Banco da v1 nao encontrado: {database_path}")

    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)

    try:
        connection.row_factory = sqlite3.Row
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

        if "users" not in tables:
            raise ValidationError(
                f"O arquivo {database_path} nao tem tabela `users`. E mesmo o banco da v1?"
            )

        return [
            LegacyUser(
                id=row["id"],
                email=row["email"],
                password_hash=row["password_hash"],
                created_at=row["created_at"],
            )
            for row in connection.execute(
                "SELECT id, email, password_hash, created_at FROM users ORDER BY id"
            )
        ]
    finally:
        connection.close()


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.now(UTC)

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def migrate_users(
    session: AsyncSession,
    legacy_users: list[LegacyUser],
    *,
    plan: str,
    apply_changes: bool,
) -> MigrationReport:
    report = MigrationReport()
    existing_emails = {email for (email,) in (await session.execute(select(User.email))).all()}

    for legacy_user in legacy_users:
        try:
            email = validate_email(legacy_user.email)
        except ValidationError as error:
            report.skipped.append((legacy_user.email, error.message))
            continue

        if not legacy_user.password_hash.startswith(ARGON2_PREFIX):
            report.skipped.append(
                (legacy_user.email, "hash de senha nao e argon2; a v2 nao consegue verificar")
            )
            continue

        if email in existing_emails:
            report.already_present.append(email)
            continue

        if apply_changes:
            session.add(
                User(
                    id=uuid.uuid4(),
                    email=email,
                    password_hash=legacy_user.password_hash,
                    plan_tier=plan,
                    is_active=True,
                    created_at=parse_timestamp(legacy_user.created_at),
                )
            )

        existing_emails.add(email)
        report.migrated.append(email)

    if apply_changes and report.migrated:
        await session.flush()

    return report


async def migrate(
    legacy_users: list[LegacyUser],
    *,
    settings: Settings,
    plan: str,
    apply_changes: bool,
) -> MigrationReport:
    init_engine(settings)

    try:
        async with session_scope() as session:
            report = await migrate_users(
                session, legacy_users, plan=plan, apply_changes=apply_changes
            )

            if not apply_changes:
                await session.rollback()

            return report
    finally:
        await dispose_engine()


def print_report(report: MigrationReport, *, apply_changes: bool, plan: str) -> None:
    section("Resultado")

    mode = (
        Style.success("APLICADO")
        if apply_changes
        else Style.warning("SIMULACAO (use --apply para gravar)")
    )
    print(f"  modo       : {mode}")
    print(f"  lidos      : {report.total_read}")
    print(f"  migrados   : {len(report.migrated)} (plano {plan})")
    print(f"  ja existiam: {len(report.already_present)}")
    print(f"  ignorados  : {len(report.skipped)}")

    if report.migrated:
        print(f"\n  {Style.bold('Migrados')}")
        for email in report.migrated:
            print(f"    {Style.success('+')} {email}")

    if report.already_present:
        print(f"\n  {Style.bold('Ja existiam no destino (pulados)')}")
        for email in report.already_present:
            print(Style.dim(f"    = {email}"))

    if report.skipped:
        print(f"\n  {Style.bold('Ignorados')}")
        for email, reason in report.skipped:
            print(f"    {Style.warning('!')} {email or '(vazio)'} - {reason}")

    if report.migrated and apply_changes:
        print(
            f"\n  {Style.success('As senhas continuam valendo')} - ninguem precisa redefinir. "
            "O hash argon2id da v1 e verificavel pela v2."
        )


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()

    section("Origem e destino")
    source_path = Path(args.source)

    print(f"  v1 (origem) : {source_path}")
    print(f"  v2 (destino): {settings.database_url.split('@')[-1]}")

    if settings.database_url.startswith("sqlite"):
        print(
            Style.warning(
                "  Aviso: o destino tambem e SQLite. Em producao a v2 usa Postgres; "
                "confira DATABASE_URL."
            )
        )

    try:
        legacy_users = read_legacy_users(source_path)
    except ValidationError as error:
        print(Style.failure(f"\n  {error.message}"))
        return 1

    print(f"  usuarios na v1: {len(legacy_users)}")

    if not legacy_users:
        print(Style.warning("  Nada a migrar."))
        return 0

    try:
        report = await migrate(
            legacy_users, settings=settings, plan=args.plan, apply_changes=args.apply
        )
    except Exception as error:
        print(Style.failure(f"\n  Falha ao acessar o banco da v2: {error}"))
        print(Style.dim("  O banco da v1 nao foi tocado (aberto somente para leitura)."))
        return 1

    print_report(report, apply_changes=args.apply, plan=args.plan)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m legacydoc_cli.migrate_v1",
        description=(
            "Copia usuarios do SQLite da v1 para o Postgres da v2. "
            "Os bancos permanecem separados; a v1 e aberta somente para leitura."
        ),
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Caminho do legacydoc.db da v1")
    parser.add_argument(
        "--plan",
        default=str(PlanTier.FREE),
        choices=[str(tier) for tier in PlanTier],
        help="Plano atribuido aos usuarios migrados",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava de verdade. Sem esta flag, apenas simula.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        exit_code = asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\ninterrompido")
        exit_code = 130

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
