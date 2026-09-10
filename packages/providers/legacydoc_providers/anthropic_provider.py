"""Anthropic (Claude) adapter.

Uses structured outputs through `messages.parse(output_format=...)`, which
validates the response against the Pydantic model and returns `parsed_output`.

Deliberately avoids forced tool use: it was the old way to extract JSON from
Claude, but current models removed it and return 400. Structured outputs is the
supported path.
"""

from __future__ import annotations

import time

from anthropic import (
    APIConnectionError,
    APIStatusError,
    AsyncAnthropic,
    RateLimitError,
)
from legacydoc_core.errors import ProviderError, ProviderRateLimitError

from legacydoc_providers.base import (
    CompletionRequest,
    StructuredResult,
    T,
    Usage,
    parse_model_json,
    to_strict_json_schema,
)

_NAME = "anthropic"


class AnthropicProvider:
    name = _NAME

    def __init__(self, api_key: str, *, timeout: float = 120.0, max_retries: int = 2) -> None:
        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=max_retries)

    async def complete_structured(
        self,
        request: CompletionRequest,
        schema: type[T],
    ) -> StructuredResult[T]:
        started = time.perf_counter()

        try:
            response = await self._client.messages.parse(
                model=request.model,
                max_tokens=request.max_output_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
                output_format=schema,
            )

            # Safety classifiers can refuse with HTTP 200.
            if getattr(response, "stop_reason", None) == "refusal":
                details = getattr(response, "stop_details", None)
                category = getattr(details, "category", None)
                raise ProviderError(
                    "Claude recusou a requisicao.",
                    details={"category": category},
                )

            value = getattr(response, "parsed_output", None)
            raw_text = _first_text_block(response)

            if value is None:
                value = parse_model_json(raw_text, schema, provider=_NAME)

        except (AttributeError, NotImplementedError):
            value, raw_text, response = await self._complete_with_output_config(request, schema)

        except RateLimitError as exc:
            raise ProviderRateLimitError("Anthropic: limite de requisicoes atingido.") from exc

        except APIConnectionError as exc:
            raise ProviderError(f"Anthropic: falha de conexao: {exc}") from exc

        except APIStatusError as exc:
            raise ProviderError(
                f"Anthropic respondeu {exc.status_code}.",
                details={"body": str(exc)[:500]},
            ) from exc

        return StructuredResult(
            value=value,
            provider=_NAME,
            model=request.model,
            usage=_extract_usage(response),
            latency_ms=int((time.perf_counter() - started) * 1000),
            raw_text=raw_text,
        )

    async def _complete_with_output_config(self, request: CompletionRequest, schema: type[T]):
        """Fallback for SDKs without the `.parse()` helper.

        `output_config.format` guarantees the first text block is schema-valid
        JSON.
        """
        response = await self._client.messages.create(
            model=request.model,
            max_tokens=request.max_output_tokens,
            system=request.system,
            messages=[{"role": "user", "content": request.user}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": to_strict_json_schema(schema),
                }
            },
        )
        raw_text = _first_text_block(response)
        return parse_model_json(raw_text, schema, provider=_NAME), raw_text, response

    async def aclose(self) -> None:
        await self._client.close()


def _first_text_block(response: object) -> str:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return ""


def _extract_usage(response: object) -> Usage:
    usage = getattr(response, "usage", None)

    if usage is None:
        return Usage()

    return Usage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )
