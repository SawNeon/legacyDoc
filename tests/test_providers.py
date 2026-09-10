"""Multi-provider routing tests.

Fake providers, so fallback logic and accounting are proven without spending
money or depending on the network.
"""

from __future__ import annotations

import pytest
from legacydoc_core.errors import ProviderError, ProviderRateLimitError
from legacydoc_providers.base import (
    CompletionRequest,
    StructuredResult,
    Usage,
    parse_model_json,
    to_strict_json_schema,
)
from legacydoc_providers.catalog import ProviderName, estimate_cost_usd, unverified_models
from legacydoc_providers.router import (
    AgentRole,
    CallRecord,
    ModelChoice,
    ProviderRouter,
    RoutePolicy,
)
from pydantic import BaseModel


class Answer(BaseModel):
    text: str
    score: int = 0


class FakeProvider:
    def __init__(self, name: str, *, fails_with: Exception | None = None) -> None:
        self.name = name
        self._fails_with = fails_with
        self.calls = 0
        self.closed = False

    async def complete_structured(self, request: CompletionRequest, schema):
        self.calls += 1

        if self._fails_with is not None:
            raise self._fails_with

        return StructuredResult(
            value=schema(text=f"resposta de {self.name}"),
            provider=self.name,
            model=request.model,
            usage=Usage(input_tokens=100, output_tokens=50),
            latency_ms=12,
        )

    async def aclose(self) -> None:
        self.closed = True


def _router(providers, routes=None, sink=None) -> ProviderRouter:
    return ProviderRouter(providers, routes=routes, usage_sink=sink)


async def test_primary_provider_is_used_when_healthy():
    openai = FakeProvider("openai")
    anthropic = FakeProvider("anthropic")

    router = _router(
        {ProviderName.OPENAI: openai, ProviderName.ANTHROPIC: anthropic},
        routes={
            AgentRole.WRITER: RoutePolicy(
                [
                    ModelChoice(ProviderName.OPENAI, "gpt-4o-mini"),
                    ModelChoice(ProviderName.ANTHROPIC, "claude-sonnet-5"),
                ]
            )
        },
    )

    result = await router.complete(AgentRole.WRITER, system="s", user="u", schema=Answer)

    assert result.provider == "openai"
    assert result.fallback_used is False
    assert anthropic.calls == 0


async def test_rate_limited_provider_falls_back_to_next():
    """Multi-provider has to be an operational advantage, not a menu option."""
    openai = FakeProvider("openai", fails_with=ProviderRateLimitError("429"))
    anthropic = FakeProvider("anthropic")

    router = _router(
        {ProviderName.OPENAI: openai, ProviderName.ANTHROPIC: anthropic},
        routes={
            AgentRole.WRITER: RoutePolicy(
                [
                    ModelChoice(ProviderName.OPENAI, "gpt-4o-mini"),
                    ModelChoice(ProviderName.ANTHROPIC, "claude-sonnet-5"),
                ]
            )
        },
    )

    result = await router.complete(AgentRole.WRITER, system="s", user="u", schema=Answer)

    assert result.provider == "anthropic"
    assert result.fallback_used is True
    assert openai.calls == 1


async def test_error_is_raised_only_after_the_whole_chain_fails():
    router = _router(
        {
            ProviderName.OPENAI: FakeProvider("openai", fails_with=ProviderError("caiu")),
            ProviderName.ANTHROPIC: FakeProvider("anthropic", fails_with=ProviderError("caiu")),
        },
        routes={
            AgentRole.WRITER: RoutePolicy(
                [
                    ModelChoice(ProviderName.OPENAI, "gpt-4o-mini"),
                    ModelChoice(ProviderName.ANTHROPIC, "claude-sonnet-5"),
                ]
            )
        },
    )

    with pytest.raises(ProviderError, match="Todos os provedores falharam"):
        await router.complete(AgentRole.WRITER, system="s", user="u", schema=Answer)


async def test_chain_is_filtered_to_configured_providers():
    """The policy names a vendor with no key configured: it must not die."""
    router = _router(
        {ProviderName.OPENAI: FakeProvider("openai")},
        routes={
            AgentRole.VERIFIER: RoutePolicy(
                [
                    ModelChoice(ProviderName.ANTHROPIC, "claude-opus-5"),
                    ModelChoice(ProviderName.OPENAI, "gpt-4o"),
                ]
            )
        },
    )

    chain = router.resolve_chain(AgentRole.VERIFIER)

    assert [choice.provider for choice in chain] == [ProviderName.OPENAI]


async def test_role_without_available_model_uses_generic_route():
    router = _router({ProviderName.OPENAI: FakeProvider("openai")})

    chain = router.resolve_chain(AgentRole.IMPROVER)

    assert chain, "degraded documentation beats a dead job"
    assert all(choice.provider == ProviderName.OPENAI for choice in chain)


async def test_router_requires_at_least_one_provider():
    with pytest.raises(ProviderError, match="Nenhum provedor"):
        ProviderRouter({})


async def test_usage_is_recorded_for_success_and_failure():
    records: list[CallRecord] = []

    async def sink(record: CallRecord) -> None:
        records.append(record)

    router = _router(
        {
            ProviderName.OPENAI: FakeProvider("openai", fails_with=ProviderError("caiu")),
            ProviderName.ANTHROPIC: FakeProvider("anthropic"),
        },
        routes={
            AgentRole.WRITER: RoutePolicy(
                [
                    ModelChoice(ProviderName.OPENAI, "gpt-4o-mini"),
                    ModelChoice(ProviderName.ANTHROPIC, "claude-sonnet-5"),
                ]
            )
        },
        sink=sink,
    )

    await router.complete(AgentRole.WRITER, system="s", user="u", schema=Answer)

    assert [record.succeeded for record in records] == [False, True]
    assert records[1].cost_usd > 0, "a successful call must record cost"


async def test_aclose_closes_every_provider():
    openai = FakeProvider("openai")
    router = _router({ProviderName.OPENAI: openai})

    await router.aclose()

    assert openai.closed is True


# ------------------------------------------------------------------ schema


def test_strict_schema_marks_every_field_required():
    schema = to_strict_json_schema(Answer)

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"text", "score"}, (
        "modo estrito exige todos os campos, mesmo os que tem default no Pydantic"
    )


def test_json_parsing_tolerates_markdown_fences():
    parsed = parse_model_json('```json\n{"text": "oi", "score": 3}\n```', Answer, provider="teste")

    assert parsed.text == "oi"
    assert parsed.score == 3


def test_json_parsing_recovers_from_leading_prose():
    parsed = parse_model_json(
        'Claro! Aqui esta:\n{"text": "oi", "score": 1}', Answer, provider="teste"
    )

    assert parsed.text == "oi"


def test_invalid_json_raises_provider_error():
    with pytest.raises(ProviderError, match="nao devolveu JSON valido"):
        parse_model_json("isto nao e json", Answer, provider="teste")


def test_json_outside_schema_raises_provider_error():
    with pytest.raises(ProviderError, match="fora do schema"):
        parse_model_json('{"campo_errado": 1}', Answer, provider="teste")


# ---------------------------------------------------------------- catalogo


def test_cost_is_computed_from_the_catalog():
    # claude-opus-5: 5 USD/MTok de entrada, 25 de saida.
    cost = estimate_cost_usd("claude-opus-5", 1_000_000, 1_000_000)

    assert cost == pytest.approx(30.0)


def test_unknown_model_costs_zero_instead_of_crashing():
    assert estimate_cost_usd("modelo-inexistente", 1000, 1000) == 0.0


def test_unverified_prices_are_flagged():
    """Guard against billing with guessed prices.

    This does not fail today: it documents which prices still need checking
    against each vendor's official table.
    """
    pendentes = {spec.model_id for spec in unverified_models()}

    assert "claude-opus-5" not in pendentes, "os precos da Anthropic vieram de fonte datada"
    assert pendentes, "check OpenAI and Google pricing before billing customers"
