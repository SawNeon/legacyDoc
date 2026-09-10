"""Common contract for LLM providers.

The three SDKs expose structured output in incompatible ways: JSON Schema in
`response_format`, forced tool use, and `response_schema`. This module hides
the difference behind one call so agents never know which vendor answered.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from legacydoc_core.errors import ProviderError
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    cache_read_tokens: int = 0
    """Input tokens served from the provider cache, billed at a fraction."""

    cache_write_tokens: int = 0
    """Input tokens written to the cache, billed at a premium."""

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass
class StructuredResult(Generic[T]):
    """A response already validated against the requested schema, plus telemetry."""

    value: T
    provider: str
    model: str
    usage: Usage
    latency_ms: int
    raw_text: str = ""
    fallback_used: bool = False
    """True when the primary provider failed and the router fell back."""


MIN_CACHEABLE_TOKENS = 1024
"""Below this, providers silently skip the cache.

Marking a shorter prefix is worse than not marking it: a cache write costs
more than a plain input token, so the request pays a premium for a cache
that is never created.
"""

CHARS_PER_TOKEN = 3.6


def is_worth_caching(text: str) -> bool:
    return len(text) / CHARS_PER_TOKEN >= MIN_CACHEABLE_TOKENS


@dataclass(frozen=True)
class CompletionRequest:
    system: str
    user: str
    model: str
    temperature: float = 0.1
    max_output_tokens: int = 4096

    cacheable_prefix: str = ""
    """Stable content placed before `user` and offered to the provider cache.

    Caching is prefix-based, so this only pays off when the same text leads
    several requests. The orchestrator uses it for the file source in the
    audit loop, which is resent unchanged on every review round.
    """

    cache_key: str = ""
    """Groups requests sharing a prefix, improving cache routing."""

    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def should_cache_prefix(self) -> bool:
        return bool(self.cacheable_prefix) and is_worth_caching(self.cacheable_prefix)

    @property
    def user_content(self) -> str:
        """Prefix and variable part joined, for providers without block caching."""
        if not self.cacheable_prefix:
            return self.user

        return "\n\n".join([self.cacheable_prefix, self.user])


@runtime_checkable
class LLMProvider(Protocol):
    """A model vendor."""

    name: str

    async def complete_structured(
        self,
        request: CompletionRequest,
        schema: type[T],
    ) -> StructuredResult[T]: ...

    async def aclose(self) -> None: ...


# --------------------------------------------------------------- utilidades


def to_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic model into JSON Schema accepted in strict mode.

    Strict mode and `response_schema` require every object to declare
    `additionalProperties: false` and list all properties in `required`.
    Pydantic marks defaulted fields optional, so the tree is rewritten.
    """
    schema = model.model_json_schema()
    _tighten(schema, schema.get("$defs", {}))
    return schema


def _tighten(node: Any, defs: dict[str, Any]) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())

        # Strict mode rejects these validation keywords.
        for unsupported in ("minLength", "maxLength", "minimum", "maximum", "format"):
            node.pop(unsupported, None)

        for value in node.values():
            _tighten(value, defs)

    elif isinstance(node, list):
        for item in node:
            _tighten(item, defs)


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_model_json(raw: str, schema: type[T], *, provider: str) -> T:
    """Validate raw text against the schema, tolerating markdown fences.

    Models occasionally wrap JSON in a code fence despite instructions. Cleaning
    the response is cheaper than burning another paid call.
    """
    text = raw.strip()

    if not text:
        raise ProviderError(f"{provider} devolveu resposta vazia.")

    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        # Ultimo recurso: recorta do primeiro '{' ao ultimo '}'.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ProviderError(
                f"{provider} nao devolveu JSON valido.",
                details={"raw_preview": text[:500]},
            ) from exc
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as inner:
            raise ProviderError(
                f"{provider} nao devolveu JSON valido.",
                details={"raw_preview": text[:500]},
            ) from inner

    try:
        return schema.model_validate(payload)
    except PydanticValidationError as exc:
        raise ProviderError(
            f"{provider} devolveu JSON fora do schema {schema.__name__}.",
            details={"errors": exc.errors()[:5]},
        ) from exc


def json_instruction(schema: type[BaseModel]) -> str:
    """Format instruction for providers without native strict mode."""
    return (
        "Responda EXCLUSIVAMENTE com um objeto JSON valido que satisfaca este "
        "JSON Schema. Sem texto antes ou depois, sem cercas de markdown.\n\n"
        f"{json.dumps(to_strict_json_schema(schema), ensure_ascii=False)}"
    )
