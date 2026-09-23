"""Database models.

Postgres is the production target; column types use variants so the test
suite can run on SQLite without a container.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from legacydoc_core.plans import GenerationDepth

JSONType = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------- enums


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


class JobType(StrEnum):
    DOCUMENT_REPOSITORY = "document_repository"
    """Clone a repository and document the selected files."""

    DOCUMENT_SNIPPET = "document_snippet"
    """Document code sent inline. Used by the VS Code extension."""

    DOCUMENT_ARCHIVE = "document_archive"
    """Document an uploaded archive, for code that is not on GitHub."""


class FindingCategory(StrEnum):
    COMPLEXITY = "complexity"
    MAINTAINABILITY = "maintainability"
    CORRECTNESS = "correctness"
    SECURITY = "security"
    PERFORMANCE = "performance"
    TESTING = "testing"
    DOCUMENTATION = "documentation"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ContextKind(StrEnum):
    GLOSSARY = "glossary"
    ARCHITECTURE = "architecture"
    CONVENTION = "convention"
    DOMAIN_RULE = "domain_rule"
    DEPENDENCY = "dependency"
    FREEFORM = "freeform"


# -------------------------------------------------------------------- tabelas


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    plan_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    """Acesso ao painel de contas.

    Uma marca booleana, e nao um sistema de papeis: a equipe tem cinco pessoas,
    e papel com permissao granular sem ninguem para diferenciar so acrescenta
    codigo que ninguem exercita. A promocao acontece apenas pela linha de
    comando, nunca por HTTP, para que ganhar privilegio nao seja uma rota que
    alguem possa alcancar.
    """

    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """Reset on every successful login."""

    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Temporary lock after consecutive failures.

    Protects the account rather than the IP: a distributed attack rotates
    addresses but keeps targeting one email. Per-IP limiting is handled by
    nginx before the request reaches the application.
    """

    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class ApiKey(Base, TimestampMixin):
    """Long-lived credential for the VS Code extension and CI integrations.

    Only the hash is stored. `prefix` holds the leading characters of the
    plaintext key so lookups avoid a table scan and the UI can show a
    truncated value.
    """

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="api_keys")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class PasswordResetToken(Base):
    """Single-use password reset token.

    Only the hash is stored, so database access alone cannot reset a password.
    The plaintext exists only in the emailed link.
    """

    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_password_reset_user", "user_id", "used_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("owner_id", "slug", name="uq_projects_owner_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    repo_url: Mapped[str | None] = mapped_column(String(500))
    default_branch: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[User] = relationship(back_populates="projects")
    context_items: Mapped[list[ContextItem]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ContextItem(Base, TimestampMixin):
    """Project context injected into agent prompts.

    Clients register glossaries, architecture decisions and conventions; the
    orchestrator selects the relevant entries per file before calling the LLM.
    """

    __tablename__ = "context_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default=ContextKind.FREEFORM)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    path_globs: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    """When set, the item only reaches files matching one of these globs."""

    tags: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)

    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    """Tie-breaker when the context budget is exceeded. Higher wins."""

    project: Mapped[Project] = relationship(back_populates="context_items")


class Job(Base, TimestampMixin):
    """Asynchronous unit of work.

    This table is the queue: workers claim rows with
    SELECT ... FOR UPDATE SKIP LOCKED. There is no separate broker, so a job
    is only lost if the database is lost.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "status", "priority", "scheduled_at"),
        Index("ix_jobs_user_created", "user_id", "created_at"),
        CheckConstraint("attempts >= 0", name="ck_jobs_attempts_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )

    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=JobStatus.QUEUED)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    params: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    """When the job becomes eligible. Drives retry backoff."""

    locked_by: Mapped[str | None] = mapped_column(String(120))

    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    """Past this instant without a heartbeat, another worker may claim it."""

    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_message: Mapped[str | None] = mapped_column(String(300))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)

    webhook_url: Mapped[str | None] = mapped_column(String(500))

    documents: Mapped[list[Document]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Document(Base, TimestampMixin):
    """Documentation generated for a single file."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("job_id", "path", name="uq_documents_job_path"),
        Index("ix_documents_project_path", "project_id", "path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    language: Mapped[str] = mapped_column(String(40), nullable=False)

    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    """Allows skipping reprocessing when the file is unchanged."""

    summary: Mapped[str | None] = mapped_column(Text)

    symbols: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    """Serialized SymbolDoc list: functions, classes and methods."""

    depth: Mapped[str] = mapped_column(
        String(20), nullable=False, default=str(GenerationDepth.BASIC)
    )
    """Which analysis actually produced this document.

    Stored per document rather than read back from the job, so the answer
    survives a plan change and the front can label each card without a second
    request.
    """

    markdown: Mapped[str | None] = mapped_column(Text)

    findings: Mapped[list[Finding]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    job: Mapped[Job] = relationship(back_populates="documents")


class Finding(Base, TimestampMixin):
    """Improvement finding produced by the Improver agent.

    Only visible on plans that allow IMPROVEMENT_FINDINGS, but always stored so
    an upgrade reveals prior analysis without reprocessing.
    """

    __tablename__ = "findings"
    __table_args__ = (Index("ix_findings_document_severity", "document_id", "severity"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    category: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text)
    symbol_name: Mapped[str | None] = mapped_column(String(300))
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    document: Mapped[Document] = relationship(back_populates="findings")


class UsageRecord(Base):
    """One row per LLM call. Basis for billing and cost diagnostics."""

    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))

    agent: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdminAction(Base):
    """Registro de toda acao administrativa sobre uma conta.

    Existe porque daqui a tres meses ninguem vai lembrar por que uma conta esta
    no plano Team. E quando a cobranca entrar, o gateway passa a mandar o plano
    pelo webhook: sem este registro, uma troca feita na mao vira um conflito
    silencioso entre o que a pessoa pagou e o que ela tem.

    O e-mail do autor e do alvo sao copiados no momento da acao. A chave
    estrangeira sozinha nao basta: se a conta for apagada, o registro
    continuaria existindo sem dizer de quem era.
    """

    __tablename__ = "admin_actions"
    __table_args__ = (Index("ix_admin_actions_target", "target_user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_email: Mapped[str] = mapped_column(String(320), nullable=False)

    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    target_email: Mapped[str] = mapped_column(String(320), nullable=False)

    action: Mapped[str] = mapped_column(String(40), nullable=False)
    value_before: Mapped[str | None] = mapped_column(String(120))
    value_after: Mapped[str | None] = mapped_column(String(120))

    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    """Obrigatorio. Uma troca de plano sem motivo escrito e a que ninguem
    consegue explicar depois."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
