"""Google Gemini adapter."""

from __future__ import annotations

import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from legacydoc_core.errors import ProviderError, ProviderRateLimitError

from legacydoc_providers.base import (
    CompletionRequest,
    StructuredResult,
    T,
    Usage,
    parse_model_json,
    to_strict_json_schema,
)

_NAME = "gemini"


class GeminiProvider:
    name = _NAME

    def __init__(self, api_key: str, *, timeout: float = 120.0, max_retries: int = 2) -> None:
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=int(timeout * 1000)),
        )
        self._max_retries = max_retries

    async def complete_structured(
        self,
        request: CompletionRequest,
        schema: type[T],
    ) -> StructuredResult[T]:
        started = time.perf_counter()

        config = genai_types.GenerateContentConfig(
            system_instruction=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            response_mime_type="application/json",
            response_schema=to_strict_json_schema(schema),
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=request.model,
                contents=request.user_content,
                config=config,
            )
        except genai_errors.ClientError as exc:
            if getattr(exc, "code", None) == 429:
                raise ProviderRateLimitError("Gemini: limite de requisicoes atingido.") from exc
            raise ProviderError(
                f"Gemini respondeu {getattr(exc, 'code', '4xx')}.",
                details={"body": str(exc)[:500]},
            ) from exc
        except genai_errors.ServerError as exc:
            raise ProviderError(f"Gemini: erro no servidor: {exc}") from exc

        raw_text = getattr(response, "text", "") or ""

        value = parse_model_json(raw_text, schema, provider=_NAME)

        return StructuredResult(
            value=value,
            provider=_NAME,
            model=request.model,
            usage=_extract_usage(response),
            latency_ms=int((time.perf_counter() - started) * 1000),
            raw_text=raw_text,
        )

    async def aclose(self) -> None:
        return None


def _extract_usage(response: object) -> Usage:
    metadata = getattr(response, "usage_metadata", None)

    if metadata is None:
        return Usage()

    return Usage(
        input_tokens=getattr(metadata, "prompt_token_count", 0) or 0,
        output_tokens=getattr(metadata, "candidates_token_count", 0) or 0,
    )
