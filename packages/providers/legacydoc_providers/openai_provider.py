"""OpenAI adapter."""

from __future__ import annotations

import time

from legacydoc_core.errors import ProviderError, ProviderRateLimitError
from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    RateLimitError,
)

from legacydoc_providers.base import (
    CompletionRequest,
    StructuredResult,
    T,
    Usage,
    json_instruction,
    parse_model_json,
)

_NAME = "openai"


class OpenAIProvider:
    name = _NAME

    def __init__(self, api_key: str, *, timeout: float = 120.0, max_retries: int = 2) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)

    async def complete_structured(
        self,
        request: CompletionRequest,
        schema: type[T],
    ) -> StructuredResult[T]:
        started = time.perf_counter()

        try:
            response = await self._client.chat.completions.parse(
                model=request.model,
                temperature=request.temperature,
                max_completion_tokens=request.max_output_tokens,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user_content},
                ],
                response_format=schema,
                **_cache_options(request),
            )
            choice = response.choices[0]
            value = choice.message.parsed

            if value is None:
                refusal = getattr(choice.message, "refusal", None)
                if refusal:
                    raise ProviderError(f"OpenAI recusou a requisicao: {refusal}")
                value = parse_model_json(choice.message.content or "", schema, provider=_NAME)

            raw_text = choice.message.content or ""

        except (AttributeError, NotImplementedError):
            value, raw_text, response = await self._complete_json_mode(request, schema)

        except RateLimitError as exc:
            raise ProviderRateLimitError("OpenAI: limite de requisicoes atingido.") from exc

        except APIConnectionError as exc:
            raise ProviderError(f"OpenAI: falha de conexao: {exc}") from exc

        except APIStatusError as exc:
            raise ProviderError(
                f"OpenAI respondeu {exc.status_code}.",
                details={"body": str(exc)[:500]},
            ) from exc

        usage = _extract_usage(response)

        return StructuredResult(
            value=value,
            provider=_NAME,
            model=request.model,
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
            raw_text=raw_text,
        )

    async def _complete_json_mode(self, request: CompletionRequest, schema: type[T]):
        """Fallback for SDKs without `.parse()`."""
        response = await self._client.chat.completions.create(
            model=request.model,
            temperature=request.temperature,
            max_completion_tokens=request.max_output_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": f"{request.system}\n\n{json_instruction(schema)}"},
                {"role": "user", "content": request.user_content},
            ],
            **_cache_options(request),
        )
        raw_text = response.choices[0].message.content or ""
        return parse_model_json(raw_text, schema, provider=_NAME), raw_text, response

    async def aclose(self) -> None:
        await self._client.close()


def _cache_options(request: CompletionRequest) -> dict:
    """OpenAI caches automatically above its minimum; the key improves routing."""
    return {"prompt_cache_key": request.cache_key} if request.cache_key else {}


def _extract_usage(response: object) -> Usage:
    usage = getattr(response, "usage", None)

    if usage is None:
        return Usage()

    details = getattr(usage, "prompt_tokens_details", None)

    return Usage(
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        cache_read_tokens=getattr(details, "cached_tokens", 0) or 0,
    )
