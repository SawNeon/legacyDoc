"""Application configuration loaded from environment variables.

Hard rule: no secret has a usable default. Missing JWT_SECRET_KEY or
DATABASE_URL fails at import rather than starting with a public secret, which
is what v1 did when it signed tokens with a string committed to the repository.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------------- ambiente
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # -------------------------------------------------------------- banco/fila
    database_url: str = Field(
        ...,
        description="DSN async do Postgres, ex: postgresql+asyncpg://user:pass@host:5432/legacydoc",
    )
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=5, ge=0, le=100)

    # -------------------------------------------------------------------- auth
    jwt_secret_key: SecretStr = Field(..., min_length=32)
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=1440, ge=5)
    min_password_length: int = Field(default=10, ge=8)

    # --------------------------------------------------------------------- api
    allowed_origins: str = Field(default="http://localhost:5173")
    api_root_path: str = Field(default="")

    # ------------------------------------------------------------------ e-mail
    email_backend: str = Field(default="console")
    """`console` writes to the log and needs no provider; `smtp` delivers."""

    email_from: str = Field(default="Legacy Doc <nao-responda@legacydoc.com.br>")
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: SecretStr | None = Field(default=None)

    frontend_base_url: str = Field(default="http://localhost:5173")
    """Base URL for the emailed password reset link."""

    # -------------------------------------------------------------- provedores
    openai_api_key: SecretStr | None = Field(default=None)
    anthropic_api_key: SecretStr | None = Field(default=None)
    gemini_api_key: SecretStr | None = Field(default=None)
    provider_timeout_seconds: float = Field(default=120.0, gt=0)
    provider_max_retries: int = Field(default=2, ge=0, le=5)

    # ----------------------------------------------------------------- ingestao
    storage_dir: Path = Field(default=Path("./var/storage"))
    tmp_dir: Path = Field(default=Path("./var/tmp"))
    max_source_file_bytes: int = Field(default=512 * 1024, gt=0)
    max_repo_files: int = Field(default=2000, gt=0)
    max_repo_bytes: int = Field(default=250 * 1024 * 1024, gt=0)
    clone_timeout_seconds: int = Field(default=300, gt=0)

    upload_dir: Path = Field(default=Path("./var/uploads"))
    """Where uploads wait for the worker. Cleared after processing."""

    max_upload_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    """Ceiling for the compressed upload; expanded content uses max_repo_bytes."""

    max_archive_entries: int = Field(default=5000, gt=0)
    """Entry ceiling for an archive, guarding against inode exhaustion."""

    global_monthly_budget_usd: float = Field(default=50.0, gt=0)
    """Spend ceiling for the entire system per month.

    Last line of defense for the credit card: even with every user inside their
    own limit, a hundred of them can add up past what the operator can pay.
    Once reached, no new job is accepted until the month rolls over.
    """

    rate_limit_enabled: bool = Field(default=True)
    """Per-IP throttling inside the application.

    Kept on by default so the API is protected wherever it runs, including
    without nginx in front of it.
    """

    trust_proxy_headers: bool = Field(default=False)
    """Whether X-Forwarded-For may be believed.

    Only true when a reverse proxy the operator controls sits in front and
    rewrites the header. With it on and no such proxy, any caller can forge an
    address and hand itself a fresh allowance.
    """

    # ------------------------------------------------------------------ worker
    worker_concurrency: int = Field(default=4, ge=1, le=64)
    worker_poll_interval_seconds: float = Field(default=2.0, gt=0)
    job_lease_seconds: int = Field(default=900, gt=0)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    chunk_concurrency: int = Field(default=6, ge=1, le=32)

    @field_validator("allowed_origins")
    @classmethod
    def _reject_wildcard_origin(cls, value: str) -> str:
        if "*" in value:
            raise ValueError(
                "ALLOWED_ORIGINS nao pode conter '*': a API usa credenciais e "
                "curinga desativa a protecao de origem do navegador."
            )
        return value

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        if not value.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
            raise ValueError(
                "DATABASE_URL precisa usar um driver async "
                "(postgresql+asyncpg:// em producao, sqlite+aiosqlite:// em teste)."
            )
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    def configured_providers(self) -> set[str]:
        """Providers with a key present, used to validate agent routes."""
        present: set[str] = set()
        if self.openai_api_key:
            present.add("openai")
        if self.anthropic_api_key:
            present.add("anthropic")
        if self.gemini_api_key:
            present.add("gemini")
        return present


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
