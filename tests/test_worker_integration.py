"""Integration: from the queue to stored documents.

Exercises the full worker path without spending tokens or touching the network:
the provider router is replaced by a double returning scripted responses.
"""

from __future__ import annotations

import pytest
from legacydoc_core.domain import (
    FindingDraft,
    ImproverOutput,
    SummarizerOutput,
    SymbolDoc,
    VerifierOutput,
    WriterOutput,
)
from legacydoc_core.models import Document, Finding, Job, JobStatus, UsageRecord
from legacydoc_core.queue import claim_job, complete_job, enqueue
from legacydoc_providers.base import StructuredResult, Usage
from legacydoc_providers.catalog import estimate_cost_usd
from legacydoc_providers.router import AgentRole, CallRecord
from legacydoc_worker.processor import JobProcessor
from sqlalchemy import select

SOURCE = (
    "class Carrinho:\n"
    "    def adicionar(self, item, quantidade):\n"
    "        if quantidade <= 0:\n"
    "            raise ValueError('quantidade invalida')\n"
    "        self.itens.append(item)\n"
    "        return len(self.itens)\n"
    "\n"
    "def calcular_total(itens):\n"
    "    return sum(i.preco for i in itens)\n"
)


class FakeRouter:
    """Stand-in for ProviderRouter, answering per role.

    Honours `usage_sink` like the real router: without it the billing test
    would measure the double instead of the processor wiring.
    """

    def __init__(self, usage_sink=None) -> None:
        self.calls: list[AgentRole] = []
        self.closed = False
        self._usage_sink = usage_sink

    async def complete(self, role, *, system, user, schema):
        self.calls.append(role)

        result = StructuredResult(
            value=self._value_for(role, schema),
            provider="fake",
            model="claude-sonnet-5",
            usage=Usage(input_tokens=800, output_tokens=200),
            latency_ms=25,
        )

        if self._usage_sink is not None:
            await self._usage_sink(
                CallRecord(
                    agent=str(role),
                    provider=result.provider,
                    model=result.model,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    cost_usd=estimate_cost_usd(
                        result.model,
                        result.usage.input_tokens,
                        result.usage.output_tokens,
                    ),
                    latency_ms=result.latency_ms,
                    succeeded=True,
                )
            )

        return result

    def _value_for(self, role, schema):
        if role == AgentRole.WRITER:
            return WriterOutput(
                symbols=[
                    SymbolDoc(
                        name="adicionar",
                        kind="function",
                        signature="def adicionar(self, item, quantidade)",
                        language="python",
                        summary="Adiciona um item ao carrinho.",
                        description="Situacao, acao e impacto.",
                        raises=["ValueError"],
                    ),
                    SymbolDoc(
                        name="calcular_total",
                        kind="function",
                        signature="def calcular_total(itens)",
                        language="python",
                        summary="Soma o preco dos itens.",
                        description="Situacao, acao e impacto.",
                    ),
                ]
            )

        if role == AgentRole.IMPROVER:
            return ImproverOutput(
                findings=[
                    FindingDraft(
                        category="correctness",
                        severity="high",
                        title="Nao valida o tipo do item",
                        detail="Qualquer objeto entra na lista.",
                        suggestion="Valide antes de inserir.",
                        symbol_name="adicionar",
                        confidence=0.7,
                    )
                ]
            )

        if role == AgentRole.VERIFIER:
            return VerifierOutput(
                approved=True, audit_notes="fiel ao codigo", feedback_message="Aprovado."
            )

        if role == AgentRole.SUMMARIZER:
            return SummarizerOutput(summary="Modulo de carrinho de compras.")

        return schema(ready_to_write=True, queries="", user_facing_message="")

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_router(monkeypatch) -> FakeRouter:
    """Capture the usage_sink the processor passes, to verify the wiring."""
    holder: dict[str, FakeRouter] = {}

    def _from_settings(cls, settings, **kwargs):
        router = FakeRouter(usage_sink=kwargs.get("usage_sink"))
        holder["router"] = router
        return router

    monkeypatch.setattr(
        "legacydoc_worker.processor.ProviderRouter.from_settings",
        classmethod(_from_settings),
    )

    # Proxy: os testes inspecionam o roteador criado dentro do processor.
    class _Proxy:
        @property
        def calls(self):
            return holder["router"].calls

        @property
        def closed(self):
            return holder["router"].closed

    return _Proxy()


async def _queue_snippet_job(session, user) -> Job:
    job = await enqueue(
        session,
        user_id=user.id,
        job_type="document_snippet",
        params={
            "path": "src/carrinho.py",
            "content": SOURCE,
            "output_language": "pt-BR",
            "include_findings": True,
        },
    )
    await session.commit()

    return job


async def test_full_job_produces_document_and_findings(session, pro_user, settings, fake_router):
    await _queue_snippet_job(session, pro_user)

    claimed = await claim_job(session, worker_id="w1", lease_seconds=300)
    await session.commit()

    outcome = await JobProcessor(settings).process(session, claimed, worker_id="w1")

    await complete_job(session, job_id=claimed.id, worker_id="w1")
    await session.commit()

    assert outcome.documents_created == 1

    document = (await session.execute(select(Document))).scalar_one()
    assert document.path == "src/carrinho.py"
    assert document.language == "python"
    assert document.summary == "Modulo de carrinho de compras."
    assert document.user_id == pro_user.id, "every document needs an owner"
    assert {symbol["name"] for symbol in document.symbols} == {"adicionar", "calcular_total"}

    # Lines and complexity come from the AST, not the model.
    adicionar = next(s for s in document.symbols if s["name"] == "adicionar")
    assert adicionar["line_start"] == 2
    assert adicionar["complexity_estimate"] >= 2
    assert adicionar["parent"] == "Carrinho"

    findings = (await session.execute(select(Finding))).scalars().all()
    assert len(findings) == 1
    assert findings[0].severity == "high"

    await session.refresh(claimed)
    assert claimed.status == JobStatus.SUCCEEDED
    assert claimed.progress_percent == 100


async def test_usage_is_recorded_for_billing(session, pro_user, settings, fake_router):
    await _queue_snippet_job(session, pro_user)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=300)
    await session.commit()

    await JobProcessor(settings).process(session, claimed, worker_id="w1")
    await session.commit()

    records = (await session.execute(select(UsageRecord))).scalars().all()

    assert records, "every LLM call must record usage"
    assert all(record.job_id == claimed.id for record in records)
    assert all(record.user_id == pro_user.id for record in records)
    # claude-sonnet-5: 2 USD/MTok entrada, 10 de saida.
    assert sum(record.cost_usd for record in records) > 0


async def test_free_plan_skips_the_expensive_agents(session, user, settings, fake_router):
    """The Free plan must not pay for the improver or the verifier."""
    await _queue_snippet_job(session, user)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=300)
    await session.commit()

    await JobProcessor(settings).process(session, claimed, worker_id="w1")
    await session.commit()

    assert AgentRole.IMPROVER not in fake_router.calls
    assert AgentRole.VERIFIER not in fake_router.calls
    assert AgentRole.WRITER in fake_router.calls

    assert (await session.execute(select(Finding))).scalars().all() == []


async def test_provider_router_is_closed_after_the_job(session, pro_user, settings, fake_router):
    await _queue_snippet_job(session, pro_user)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=300)
    await session.commit()

    await JobProcessor(settings).process(session, claimed, worker_id="w1")

    assert fake_router.closed is True, "provider HTTP connections must not leak"


async def test_unsupported_extension_fails_without_retry(session, pro_user, settings, fake_router):
    from legacydoc_core.errors import ValidationError

    await enqueue(
        session,
        user_id=pro_user.id,
        job_type="document_snippet",
        params={"path": "leia.txt", "content": "oi"},
    )
    await session.commit()

    claimed = await claim_job(session, worker_id="w1", lease_seconds=300)
    await session.commit()

    with pytest.raises(ValidationError):
        await JobProcessor(settings).process(session, claimed, worker_id="w1")


async def test_document_export_works_end_to_end(session, pro_user, settings, fake_router):
    """Prove the stored result renders valid artifacts in all three formats."""
    from legacydoc_core.domain import FileDocumentation
    from legacydoc_exporters import ExporterFactory

    await _queue_snippet_job(session, pro_user)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=300)
    await session.commit()

    await JobProcessor(settings).process(session, claimed, worker_id="w1")
    await session.commit()

    document = (await session.execute(select(Document))).scalar_one()

    documentation = FileDocumentation(
        path=document.path,
        language=document.language,
        summary=document.summary or "",
        symbols=[SymbolDoc.model_validate(item) for item in document.symbols],
    )

    assert ExporterFactory.get("pdf").export(documentation).content.startswith(b"%PDF")
    assert b"adicionar" in ExporterFactory.get("markdown").export(documentation).content
    assert b"calcular_total" in ExporterFactory.get("json").export(documentation).content
