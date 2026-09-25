"""Create a demo account with sample data."""

from __future__ import annotations

import argparse
import hashlib

from legacydoc_core.db import dispose_engine, init_engine, session_scope
from legacydoc_core.errors import ValidationError
from legacydoc_core.models import (
    ApiKey,
    ContextItem,
    Document,
    Finding,
    Job,
    JobStatus,
    JobType,
    Project,
    User,
)
from legacydoc_core.plans import GenerationDepth, PlanTier, get_plan
from legacydoc_core.security import (
    generate_api_key,
    hash_password,
    validate_email,
    validate_password_strength,
)
from legacydoc_core.settings import get_settings
from sqlalchemy import select

from legacydoc_cli.console import Style, section

SAMPLE_PATH = "src/orders/checkout.py"

SAMPLE_SYMBOLS = [
    {
        "name": "finish_purchase",
        "kind": "function",
        "signature": "def finish_purchase(order, stock, postal_code)",
        "language": "python",
        "line_start": 12,
        "line_end": 34,
        "summary": "Fecha a compra validando estoque e calculando o frete.",
        "description": (
            "Situacao: o cliente confirmou o carrinho e o pedido precisa virar compra. "
            "Acao: valida o pedido contra o estoque, calcula o frete pelo CEP e devolve "
            "o total. Impacto: estoque insuficiente interrompe a compra antes da cobranca."
        ),
        "parameters": [
            {"name": "order", "type": "Order", "description": "Pedido montado pelo cliente"},
            {"name": "stock", "type": "int", "description": "Quantidade disponivel"},
            {"name": "postal_code", "type": "str", "description": "CEP de entrega"},
        ],
        "return_type": "Decimal",
        "return_description": "Valor total incluindo frete",
        "raises": ["ValueError"],
        "side_effects": ["Consulta o servico de frete"],
        "complexity_estimate": 6,
        "parent": None,
    },
    {
        "name": "validate_order",
        "kind": "function",
        "signature": "def validate_order(order, stock)",
        "language": "python",
        "line_start": 37,
        "line_end": 45,
        "summary": "Recusa pedidos acima do estoque disponivel.",
        "description": (
            "Situacao: o pedido pode pedir mais itens do que existem. Acao: compara a "
            "quantidade pedida com o estoque. Impacto: levanta ValueError antes de "
            "qualquer cobranca, evitando venda sem lastro."
        ),
        "parameters": [
            {"name": "order", "type": "Order", "description": "Pedido a validar"},
            {"name": "stock", "type": "int", "description": "Quantidade disponivel"},
        ],
        "return_type": "bool",
        "return_description": "True quando o pedido cabe no estoque",
        "raises": ["ValueError"],
        "side_effects": [],
        "complexity_estimate": 2,
        "parent": None,
    },
]

SAMPLE_FINDINGS = [
    {
        "category": "correctness",
        "severity": "high",
        "title": "Frete e calculado antes de confirmar o pagamento",
        "detail": (
            "finish_purchase consulta o servico de frete mesmo quando o pagamento ainda "
            "pode falhar, gerando chamada externa desnecessaria e custo por consulta."
        ),
        "suggestion": "Mova a consulta de frete para depois da autorizacao do pagamento.",
        "symbol_name": "finish_purchase",
        "line_start": 24,
        "line_end": 27,
        "confidence": 0.7,
    },
    {
        "category": "testing",
        "severity": "medium",
        "title": "Caminho de estoque insuficiente nao tem teste",
        "detail": "validate_order levanta ValueError, mas nenhum teste exercita esse ramo.",
        "suggestion": "Adicione um caso com quantidade maior que o estoque.",
        "symbol_name": "validate_order",
        "line_start": 40,
        "line_end": 42,
        "confidence": 0.9,
    },
]


async def command_seed_demo(args: argparse.Namespace) -> int:
    settings = get_settings()

    try:
        email = validate_email(args.email)
        validate_password_strength(args.password, settings.min_password_length)
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
                print(Style.failure(f"  {email} ja existe. Use outro --email."))
                return 1

            user = User(
                email=email,
                password_hash=hash_password(args.password),
                display_name="Conta de teste",
                plan_tier=args.plan,
            )
            session.add(user)
            await session.flush()

            generated = generate_api_key()
            session.add(
                ApiKey(
                    user_id=user.id,
                    name="chave de teste",
                    prefix=generated.prefix,
                    key_hash=generated.key_hash,
                )
            )

            project = Project(
                owner_id=user.id,
                name="Loja Legada",
                slug="loja-legada",
                repo_url="https://github.com/exemplo/loja-legada.git",
                description="Projeto de exemplo para validar a API.",
            )
            session.add(project)
            await session.flush()

            session.add(
                ContextItem(
                    project_id=project.id,
                    kind="domain_rule",
                    title="SKU e EAN",
                    content=(
                        "SKU e o codigo interno do produto. EAN e o codigo de barras "
                        "global. Nunca sao intercambiaveis."
                    ),
                    path_globs=["src/orders/**"],
                    tags=["catalogo"],
                    weight=300,
                )
            )

            job = Job(
                user_id=user.id,
                project_id=project.id,
                job_type=str(JobType.DOCUMENT_REPOSITORY),
                status=JobStatus.SUCCEEDED,
                params={"repo_url": project.repo_url, "paths": [SAMPLE_PATH]},
                progress_percent=100,
                progress_message="Concluido.",
            )
            session.add(job)
            await session.flush()

            document = Document(
                job_id=job.id,
                project_id=project.id,
                user_id=user.id,
                path=SAMPLE_PATH,
                language="python",
                content_sha256=hashlib.sha256(SAMPLE_PATH.encode()).hexdigest(),
                depth=str(GenerationDepth.PRO),
                summary=(
                    "Modulo de fechamento de compra: valida o pedido contra o estoque "
                    "e calcula o frete antes de devolver o total."
                ),
                symbols=SAMPLE_SYMBOLS,
            )
            session.add(document)

            for finding in SAMPLE_FINDINGS:
                session.add(Finding(document=document, **finding))

            await session.flush()

            _print_summary(
                email=email,
                password=args.password,
                plan_name=get_plan(PlanTier(args.plan)).display_name,
                api_key=generated.plaintext,
                project_id=str(project.id),
                document_id=str(document.id),
                job_id=str(job.id),
            )

            return 0
    finally:
        await dispose_engine()


def _print_summary(
    *,
    email: str,
    password: str,
    plan_name: str,
    api_key: str,
    project_id: str,
    document_id: str,
    job_id: str,
) -> None:
    section("Conta de teste")
    print(f"  e-mail      : {email}")
    print(f"  senha       : {password}")
    print(f"  plano       : {plan_name}")
    print(f"  chave de API: {Style.bold(api_key)}")
    print(Style.dim("                (so aparece agora; o banco guarda apenas o hash)"))

    section("Dados de exemplo")
    print(f"  projeto   : {project_id}")
    print(f"  job       : {job_id}")
    print(f"  documento : {document_id}")
    print(f"              {len(SAMPLE_SYMBOLS)} simbolos, {len(SAMPLE_FINDINGS)} findings")
    print(
        Style.dim(
            "\n  Sao dados fixos, nao saida de LLM: existem para os endpoints de\n"
            "  leitura e export responderem sem custo nenhum."
        )
    )

    section("Como usar")
    print("  GET  /v1/auth/me")
    print(f"  GET  /v1/documents/{document_id}")
    print(f"  GET  /v1/documents/{document_id}/export?format=markdown")
    print(f"  GET  /v1/projects/{project_id}/context")


def register(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "seed-demo", help="Cria conta de teste com projeto, documento e findings"
    )
    parser.add_argument("--email", default="teste@legacydoc.com.br")
    parser.add_argument("--password", default="legacydoc2026")
    parser.add_argument(
        "--plan", default=str(PlanTier.PRO), choices=[str(tier) for tier in PlanTier]
    )
    parser.set_defaults(handler=command_seed_demo)
