"""Camada multi-provedor de LLM."""

from legacydoc_providers.base import (
    CompletionRequest,
    LLMProvider,
    StructuredResult,
    Usage,
)
from legacydoc_providers.catalog import ProviderName, get_model_spec
from legacydoc_providers.router import (
    AgentRole,
    CallRecord,
    ModelChoice,
    ProviderRouter,
    RoutePolicy,
)

__all__ = [
    "AgentRole",
    "CallRecord",
    "CompletionRequest",
    "LLMProvider",
    "ModelChoice",
    "ProviderName",
    "ProviderRouter",
    "RoutePolicy",
    "StructuredResult",
    "Usage",
    "get_model_spec",
]
