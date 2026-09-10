"""Agent-to-provider routing with a fallback chain.

Each agent role has a different cost profile. The writer runs once per chunk
and dominates volume, so it goes to a cheap model; the verifier runs once per
file and has to judge fidelity, so it goes to a strong one. Binding everything
to a single model is expensive where it does not matter and weak where it does.

When the primary provider fails, the call falls through to the next entry
instead of failing the whole job, which is what makes multi-provider an
operational advantage rather than a menu option.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from legacydoc_core.errors import ProviderError, ProviderRateLimitError
from legacydoc_core.settings import Settings

from legacydoc_providers.base import (
    CompletionRequest,
    LLMProvider,
    StructuredResult,
    T,
)
from legacydoc_providers.catalog import ProviderName, estimate_cost_usd

logger = logging.getLogger(__name__)


class AgentRole(StrEnum):
    READER = "reader"
    """Diagnoses missing context before documentation starts."""

    WRITER = "writer"
    """Writes the documentation. Runs once per chunk and dominates cost."""

    IMPROVER = "improver"
    """Raises improvement findings. Requires judgement."""

    VERIFIER = "verifier"
    """Audits documentation fidelity against the code. Needs the strongest model."""

    SUMMARIZER = "summarizer"
    """Consolidates the file summary from the documented symbols."""


@dataclass(frozen=True)
class ModelChoice:
    provider: ProviderName
    model: str
    temperature: float = 0.1
    max_output_tokens: int = 4096


@dataclass
class RoutePolicy:
    """Attempt chain for a role; the first entry is the primary."""

    chain: list[ModelChoice] = field(default_factory=list)


# Politica padrao: barato no volume, forte na auditoria.
DEFAULT_ROUTES: dict[AgentRole, RoutePolicy] = {
    AgentRole.READER: RoutePolicy(
        [
            ModelChoice(ProviderName.OPENAI, "gpt-4o-mini", temperature=0.1),
            ModelChoice(ProviderName.GEMINI, "gemini-2.0-flash", temperature=0.1),
        ]
    ),
    AgentRole.WRITER: RoutePolicy(
        [
            ModelChoice(
                ProviderName.OPENAI, "gpt-4o-mini", temperature=0.2, max_output_tokens=8192
            ),
            ModelChoice(
                ProviderName.GEMINI, "gemini-2.0-flash", temperature=0.2, max_output_tokens=8192
            ),
            ModelChoice(
                ProviderName.ANTHROPIC, "claude-haiku-4-5", temperature=0.2, max_output_tokens=8192
            ),
        ]
    ),
    AgentRole.IMPROVER: RoutePolicy(
        [
            ModelChoice(
                ProviderName.ANTHROPIC, "claude-sonnet-5", temperature=0.0, max_output_tokens=8192
            ),
            ModelChoice(ProviderName.OPENAI, "gpt-4o", temperature=0.0, max_output_tokens=8192),
        ]
    ),
    AgentRole.VERIFIER: RoutePolicy(
        [
            ModelChoice(
                ProviderName.ANTHROPIC, "claude-opus-5", temperature=0.0, max_output_tokens=8192
            ),
            ModelChoice(ProviderName.OPENAI, "gpt-4o", temperature=0.0, max_output_tokens=8192),
        ]
    ),
    AgentRole.SUMMARIZER: RoutePolicy(
        [
            ModelChoice(
                ProviderName.OPENAI, "gpt-4o-mini", temperature=0.2, max_output_tokens=1024
            ),
            ModelChoice(
                ProviderName.GEMINI, "gemini-2.0-flash", temperature=0.2, max_output_tokens=1024
            ),
        ]
    ),
}


@dataclass
class CallRecord:
    """Telemetry for one call, persisted into `usage_records`."""

    agent: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    succeeded: bool


UsageSink = Callable[[CallRecord], Awaitable[None]]


class ProviderRouter:
    """Selects the provider per role and executes with fallback."""

    def __init__(
        self,
        providers: dict[ProviderName, LLMProvider],
        *,
        routes: dict[AgentRole, RoutePolicy] | None = None,
        usage_sink: UsageSink | None = None,
    ) -> None:
        if not providers:
            raise ProviderError(
                "Nenhum provedor de LLM configurado. Defina ao menos uma chave "
                "(OPENAI_API_KEY, ANTHROPIC_API_KEY ou GEMINI_API_KEY)."
            )

        self._providers = providers
        self._routes = routes or DEFAULT_ROUTES
        self._usage_sink = usage_sink

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        routes: dict[AgentRole, RoutePolicy] | None = None,
        usage_sink: UsageSink | None = None,
    ) -> ProviderRouter:
        """Instantiate only the providers that have a key configured.

        Imports are deliberately late so a deployment using one vendor does not
        need the other SDKs installed to start.
        """
        providers: dict[ProviderName, LLMProvider] = {}

        if settings.openai_api_key:
            from legacydoc_providers.openai_provider import OpenAIProvider

            providers[ProviderName.OPENAI] = OpenAIProvider(
                settings.openai_api_key.get_secret_value(),
                timeout=settings.provider_timeout_seconds,
                max_retries=settings.provider_max_retries,
            )

        if settings.anthropic_api_key:
            from legacydoc_providers.anthropic_provider import AnthropicProvider

            providers[ProviderName.ANTHROPIC] = AnthropicProvider(
                settings.anthropic_api_key.get_secret_value(),
                timeout=settings.provider_timeout_seconds,
                max_retries=settings.provider_max_retries,
            )

        if settings.gemini_api_key:
            from legacydoc_providers.gemini_provider import GeminiProvider

            providers[ProviderName.GEMINI] = GeminiProvider(
                settings.gemini_api_key.get_secret_value(),
                timeout=settings.provider_timeout_seconds,
                max_retries=settings.provider_max_retries,
            )

        return cls(providers, routes=routes, usage_sink=usage_sink)

    def available_providers(self) -> list[ProviderName]:
        return list(self._providers)

    def resolve_chain(self, role: AgentRole) -> list[ModelChoice]:
        """Effective attempt chain, filtered to the configured providers.

        When no policy entry survives the filter, falls back to any available
        provider: degraded documentation beats a dead job.
        """
        policy = self._routes.get(role, RoutePolicy())
        chain = [choice for choice in policy.chain if choice.provider in self._providers]

        if chain:
            return chain

        fallback_role = DEFAULT_ROUTES.get(AgentRole.WRITER, RoutePolicy())
        generic = [c for c in fallback_role.chain if c.provider in self._providers]

        if generic:
            logger.warning(
                "Nenhum modelo da politica de %s esta disponivel; usando rota generica.", role
            )
            return generic

        raise ProviderError(f"Nenhum provedor disponivel para o papel {role}.")

    async def complete(
        self,
        role: AgentRole,
        *,
        system: str,
        user: str,
        schema: type[T],
    ) -> StructuredResult[T]:
        """Run the role, falling through to the next provider on each failure."""
        chain = self.resolve_chain(role)
        last_error: Exception | None = None

        for attempt, choice in enumerate(chain):
            provider = self._providers[choice.provider]
            request = CompletionRequest(
                system=system,
                user=user,
                model=choice.model,
                temperature=choice.temperature,
                max_output_tokens=choice.max_output_tokens,
            )

            try:
                result = await provider.complete_structured(request, schema)
                result.fallback_used = attempt > 0

                await self._record(role, result, succeeded=True)
                return result

            except ProviderRateLimitError as exc:
                last_error = exc
                logger.warning(
                    "%s em rate limit no papel %s; tentando proximo da cadeia.",
                    choice.provider,
                    role,
                )
                await self._record_failure(role, choice)

            except ProviderError as exc:
                last_error = exc
                logger.warning(
                    "%s falhou no papel %s (%s); tentando proximo da cadeia.",
                    choice.provider,
                    role,
                    exc.message,
                )
                await self._record_failure(role, choice)

            except asyncio.CancelledError:
                raise

            except Exception as exc:  # pragma: no cover - defesa contra SDK novo
                last_error = exc
                logger.exception("Erro inesperado em %s no papel %s.", choice.provider, role)
                await self._record_failure(role, choice)

        raise ProviderError(
            f"Todos os provedores falharam para o papel {role}.",
            details={"last_error": str(last_error)[:500]},
        )

    async def _record(self, role: AgentRole, result: StructuredResult, *, succeeded: bool) -> None:
        if self._usage_sink is None:
            return

        await self._usage_sink(
            CallRecord(
                agent=str(role),
                provider=result.provider,
                model=result.model,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                cost_usd=estimate_cost_usd(
                    result.model, result.usage.input_tokens, result.usage.output_tokens
                ),
                latency_ms=result.latency_ms,
                succeeded=succeeded,
            )
        )

    async def _record_failure(self, role: AgentRole, choice: ModelChoice) -> None:
        if self._usage_sink is None:
            return

        await self._usage_sink(
            CallRecord(
                agent=str(role),
                provider=str(choice.provider),
                model=choice.model,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=0,
                succeeded=False,
            )
        )

    async def aclose(self) -> None:
        await asyncio.gather(
            *(provider.aclose() for provider in self._providers.values()),
            return_exceptions=True,
        )
