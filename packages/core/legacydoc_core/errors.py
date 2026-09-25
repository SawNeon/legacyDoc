"""Domain exceptions."""

from __future__ import annotations


class LegacyDocError(Exception):
    """Base class for every domain error."""

    code = "internal_error"
    http_status = 500

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(LegacyDocError):
    code = "not_found"
    http_status = 404


class ValidationError(LegacyDocError):
    code = "validation_error"
    http_status = 422


class AuthenticationError(LegacyDocError):
    code = "authentication_error"
    http_status = 401


class PermissionDeniedError(LegacyDocError):
    code = "permission_denied"
    http_status = 403


class ConflictError(LegacyDocError):
    code = "conflict"
    http_status = 409


class QuotaExceededError(LegacyDocError):
    """The plan forbids the operation or the period quota is exhausted."""

    code = "quota_exceeded"
    http_status = 402


class RateLimitError(LegacyDocError):
    code = "rate_limited"
    http_status = 429


class ProviderError(LegacyDocError):
    """A call to an LLM provider failed."""

    code = "provider_error"
    http_status = 502


class ProviderRateLimitError(ProviderError):
    """The provider returned 429; the router may try the next one."""

    code = "provider_rate_limited"


class UnsupportedLanguageError(LegacyDocError):
    code = "unsupported_language"
    http_status = 422
