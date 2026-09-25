"""Model catalog: capabilities and pricing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProviderName(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


@dataclass(frozen=True)
class ModelSpec:
    provider: ProviderName
    model_id: str
    context_window: int
    max_output_tokens: int
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    supports_structured_output: bool = True
    verified_at: str = ""
    verified: bool = False

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_usd_per_mtok + output_tokens * self.output_usd_per_mtok
        ) / 1_000_000


_MODELS: dict[str, ModelSpec] = {
    "claude-opus-5": ModelSpec(
        provider=ProviderName.ANTHROPIC,
        model_id="claude-opus-5",
        context_window=1_000_000,
        max_output_tokens=64_000,
        input_usd_per_mtok=5.00,
        output_usd_per_mtok=25.00,
        verified_at="2026-06-24",
        verified=True,
    ),
    "claude-sonnet-5": ModelSpec(
        provider=ProviderName.ANTHROPIC,
        model_id="claude-sonnet-5",
        context_window=1_000_000,
        max_output_tokens=64_000,
        input_usd_per_mtok=2.00,
        output_usd_per_mtok=10.00,
        verified_at="2026-06-24",
        verified=True,
    ),
    "claude-haiku-4-5": ModelSpec(
        provider=ProviderName.ANTHROPIC,
        model_id="claude-haiku-4-5",
        context_window=200_000,
        max_output_tokens=32_000,
        input_usd_per_mtok=1.00,
        output_usd_per_mtok=5.00,
        verified_at="2026-06-24",
        verified=True,
    ),
    "gpt-4o-mini": ModelSpec(
        provider=ProviderName.OPENAI,
        model_id="gpt-4o-mini",
        context_window=128_000,
        max_output_tokens=16_384,
        input_usd_per_mtok=0.15,
        output_usd_per_mtok=0.60,
        verified_at="2026-09-11",
        verified=True,
    ),
    "gpt-4o": ModelSpec(
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
        context_window=128_000,
        max_output_tokens=16_384,
        input_usd_per_mtok=2.50,
        output_usd_per_mtok=10.00,
        verified_at="2026-09-11",
        verified=True,
    ),
    "gemini-2.0-flash": ModelSpec(
        provider=ProviderName.GEMINI,
        model_id="gemini-2.0-flash",
        context_window=1_000_000,
        max_output_tokens=8_192,
        input_usd_per_mtok=0.10,
        output_usd_per_mtok=0.40,
        verified=False,
    ),
    "gemini-1.5-pro": ModelSpec(
        provider=ProviderName.GEMINI,
        model_id="gemini-1.5-pro",
        context_window=2_000_000,
        max_output_tokens=8_192,
        input_usd_per_mtok=1.25,
        output_usd_per_mtok=5.00,
        verified=False,
    ),
}


def get_model_spec(model_id: str) -> ModelSpec | None:
    return _MODELS.get(model_id)


def known_models() -> list[ModelSpec]:
    return list(_MODELS.values())


def models_for_provider(provider: ProviderName) -> list[ModelSpec]:
    return [spec for spec in _MODELS.values() if spec.provider == provider]


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated cost. An unknown model returns 0.0 rather than raising."""
    spec = _MODELS.get(model_id)
    return spec.cost_usd(input_tokens, output_tokens) if spec else 0.0


def unverified_models() -> list[ModelSpec]:
    """Used by a test that flags unverified pricing before production."""
    return [spec for spec in _MODELS.values() if not spec.verified]
