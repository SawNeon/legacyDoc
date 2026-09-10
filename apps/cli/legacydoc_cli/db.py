"""Database diagnostics and operational commands for the v2 service.

python -m legacydoc_cli.db check
python -m legacydoc_cli.db wait --timeout 60
python -m legacydoc_cli.db create-user dev@example.com --plan pro
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import time

from legacydoc_core.db import dispose_engine, init_engine, session_scope
from legacydoc_core.errors import LegacyDocError, ValidationError
from legacydoc_core.models import Document, Finding, Job, JobStatus, Project, User
from legacydoc_core.plans import PlanTier, get_plan
from legacydoc_core.security import hash_password, validate_email, validate_password_strength
from legacydoc_core.settings import Settings, get_settings
from sqlalchemy import func, inspect, select, text

from legacydoc_cli.console import Style, section
from legacydoc_cli.seed import register as register_seed_demo

EXPECTED_TABLES = {
    "users",
    "api_keys",
    "projects",
    "context_items",
    "jobs",
    "documents",
    "findings",
    "usage_records",
    "password_reset_tokens",
}

COUNTED_MODELS = (
    ("usuarios  ", User),
    ("projetos  ", Project),
    ("jobs      ", Job),
    ("documentos", Document),
    ("findings  ", Finding),
)


def redacted_target(settings: Settings) -> str:
    """The DSN without the password, safe to print in logs."""
    return settings.database_url.split("@")[-1]


async def _report_connection(engine, settings: Settings) -> bool:
    section("Conexao")
    print(f"  destino  : {redacted_target(settings)}")
    print(f"  dialeto  : {engine.dialect.name}")

    try:
        started_at = time.perf_counter()

        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            latency_ms = (time.perf_counter() - started_at) * 1000
            server_version = (
                (await connection.execute(text("SHOW server_version"))).scalar()
                if engine.dialect.name == "postgresql"
                else None
            )

        print(f"  latencia : {latency_ms:.0f}ms")

        if server_version:
            print(f"  postgres : {server_version}")

        print(f"  {Style.success('conectado')}")
        return True
    except Exception as error:
        print(f"  {Style.failure('FALHOU')}: {error}")
        return False


def _report_queue_support(engine, issues: list[str]) -> None:
    section("Capacidades exigidas pela fila")

    if engine.dialect.name == "postgresql":
        print(f"  {Style.success('OK')}  SELECT ... FOR UPDATE SKIP LOCKED disponivel")
        return

    print(
        Style.warning(
            "  ATENCAO  este dialeto nao tem SKIP LOCKED. A fila cai no modo\n"
            "           otimista, que NAO garante exclusao mutua com varios\n"
            "           workers. Aceitavel em teste, nunca em producao."
        )
    )
    issues.append("banco sem SKIP LOCKED")


async def _report_schema(engine, issues: list[str]) -> set[str]:
    section("Schema")

    async with engine.connect() as connection:
        tables = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
        missing = EXPECTED_TABLES - tables

        if missing:
            print(f"  {Style.failure('faltando')}: {', '.join(sorted(missing))}")
            print(Style.dim("  rode: alembic upgrade head"))
            issues.append("schema incompleto")
        else:
            print(f"  {Style.success('OK')}  todas as {len(EXPECTED_TABLES)} tabelas presentes")

        if "alembic_version" in tables:
            revision = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar()
            print(f"  migration: {revision}")
        else:
            print(
                Style.warning(
                    "  migration: alembic_version ausente - schema criado fora do Alembic"
                )
            )
            issues.append("sem controle de migration")

    return missing


async def _report_contents() -> None:
    section("Conteudo")

    async with session_scope() as session:
        for label, model in COUNTED_MODELS:
            total = (await session.execute(select(func.count(model.id)))).scalar_one()
            print(f"  {label}: {total}")

        running = (
            await session.execute(select(func.count(Job.id)).where(Job.status == JobStatus.RUNNING))
        ).scalar_one()

        if running:
            print(Style.warning(f"\n  {running} job(s) em execucao. Se nenhum worker estiver"))
            print(Style.warning("  rodando, o reaper vai reenfileirar quando o lease vencer."))


async def command_check(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = init_engine(settings)
    issues: list[str] = []

    if not await _report_connection(engine, settings):
        await dispose_engine()
        return 1

    _report_queue_support(engine, issues)
    missing_tables = await _report_schema(engine, issues)

    if not missing_tables:
        await _report_contents()

    await dispose_engine()

    print()

    if issues:
        print(Style.warning(f"VEREDITO: utilizavel, com ressalvas ({'; '.join(issues)})."))
        return 0 if args.tolerant else 1

    print(Style.success("VEREDITO: banco pronto."))
    return 0


async def command_wait(args: argparse.Namespace) -> int:
    """Block until the database accepts connections. Designed as a container entrypoint."""
    settings = get_settings()
    engine = init_engine(settings)

    print(f"aguardando {redacted_target(settings)} (ate {args.timeout}s)...")

    deadline = time.monotonic() + args.timeout
    attempt = 0

    while True:
        attempt += 1

        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

            print(Style.success(f"banco disponivel apos {attempt} tentativa(s)"))
            await dispose_engine()
            return 0
        except Exception as error:
            if time.monotonic() >= deadline:
                print(Style.failure(f"tempo esgotado apos {attempt} tentativas: {error}"))
                await dispose_engine()
                return 1

            print(Style.dim(f"  tentativa {attempt} falhou; nova em {args.interval}s"))
            await asyncio.sleep(args.interval)


async def command_create_user(args: argparse.Namespace) -> int:
    settings = get_settings()

    try:
        email = validate_email(args.email)
        password = args.password or getpass.getpass("Senha: ")
        validate_password_strength(password, settings.min_password_length)
    except ValidationError as error:
        print(Style.failure(f"  {error.message}"))
        return 1

    init_engine(settings)

    try:
        async with session_scope() as session:
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()

            if existing is not None:
                if not args.update:
                    print(Style.failure(f"  {email} ja existe. Use --update para alterar o plano."))
                    return 1

                previous_plan = existing.plan_tier
                existing.plan_tier = args.plan
                print(Style.success(f"  {email}: plano {previous_plan} -> {args.plan}"))
                return 0

            session.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    display_name=args.name,
                    plan_tier=args.plan,
                )
            )

        plan = get_plan(PlanTier(args.plan))
        print(Style.success(f"  conta criada: {email}"))
        print(f"  plano       : {plan.display_name}")
        print(f"  cota mensal : {plan.monthly_job_quota} jobs")
        print(f"  teto de custo: US$ {plan.monthly_cost_limit_usd:.2f}")
        print(f"  recursos    : {', '.join(sorted(str(item) for item in plan.features))}")
        return 0
    except LegacyDocError as error:
        print(Style.failure(f"  {error.message}"))
        return 1
    finally:
        await dispose_engine()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m legacydoc_cli.db",
        description="Diagnostico e operacao do banco da v2.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    check = subcommands.add_parser("check", help="Verifica conexao, schema e conteudo")
    check.add_argument(
        "--tolerant",
        action="store_true",
        help="Sai com 0 mesmo com ressalvas (util em ambiente de teste)",
    )
    check.set_defaults(handler=command_check)

    wait = subcommands.add_parser("wait", help="Espera o banco ficar disponivel")
    wait.add_argument("--timeout", type=int, default=60, help="Segundos ate desistir")
    wait.add_argument("--interval", type=float, default=2.0, help="Segundos entre tentativas")
    wait.set_defaults(handler=command_wait)

    create_user = subcommands.add_parser("create-user", help="Cria uma conta com plano definido")
    create_user.add_argument("email")
    create_user.add_argument("--password", help="Senha. Omita para digitar sem eco.")
    create_user.add_argument("--name", help="Nome de exibicao")
    create_user.add_argument(
        "--plan", default=str(PlanTier.PRO), choices=[str(tier) for tier in PlanTier]
    )
    create_user.add_argument(
        "--update", action="store_true", help="Se a conta existir, apenas troca o plano"
    )
    create_user.set_defaults(handler=command_create_user)

    register_seed_demo(subcommands)

    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        exit_code = asyncio.run(args.handler(args))
    except KeyboardInterrupt:
        print("\ninterrompido")
        exit_code = 130

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
