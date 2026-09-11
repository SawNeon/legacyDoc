"""HTTP contracts.

These models are the public API contract consumed by the VS Code extension and
the web front. A breaking change here requires a new route version.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from legacydoc_core.domain import SymbolDoc
from legacydoc_core.plans import GenerationDepth
from pydantic import BaseModel, Field

# ------------------------------------------------------------------- auth


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int


class PlanInfo(BaseModel):
    tier: str
    display_name: str
    monthly_job_quota: int
    monthly_cost_limit_usd: float
    max_files_per_job: int
    max_concurrent_jobs: int
    features: list[str]

    max_depth: str = Field(description="Analise mais profunda que este plano pode pedir.")
    available_depths: list[str] = Field(
        default_factory=list,
        description="Profundidades que este plano pode escolher, da mais barata para a mais cara. "
        "O front monta o seletor a partir desta lista em vez de fixar a ordem no codigo.",
    )


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    plan: PlanInfo
    jobs_used_this_month: int
    spent_this_month_usd: float
    """Real LLM spend this month, used by the front to show remaining budget."""


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreatedResponse(ApiKeyResponse):
    api_key: str
    """Plaintext value, shown only in this response and never recoverable."""


# --------------------------------------------------------------- projetos


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    repo_url: str | None = None
    default_branch: str | None = Field(default=None, max_length=120)
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    repo_url: str | None = None
    default_branch: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    repo_url: str | None
    default_branch: str | None
    description: str | None
    created_at: datetime


# --------------------------------------------------------------- contexto


class ContextItemCreateRequest(BaseModel):
    kind: Literal[
        "glossary", "architecture", "convention", "domain_rule", "dependency", "freeform"
    ] = "freeform"
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    path_globs: list[str] = Field(
        default_factory=list,
        description="Restringe o item a arquivos que casam, ex: ['src/auth/**']",
    )
    tags: list[str] = Field(default_factory=list)
    weight: int = Field(default=100, ge=0, le=1000)


class ContextItemResponse(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    content: str
    path_globs: list[str]
    tags: list[str]
    weight: int
    created_at: datetime


# ------------------------------------------------------------------- jobs


class RepositoryJobRequest(BaseModel):
    """Document files from a remote repository."""

    job_type: Literal["document_repository"] = "document_repository"
    repo_url: str
    branch: str | None = None
    paths: list[str] = Field(
        default_factory=list,
        description="Caminhos a documentar. Vazio processa o repositorio inteiro "
        "ate o limite do plano.",
    )
    project_id: uuid.UUID | None = None
    output_language: str = Field(default="pt-BR")
    depth: GenerationDepth | None = Field(
        default=None,
        description="Profundidade da analise. Omitido usa o maximo do plano. "
        "Pedir acima do plano nao da erro: e reduzido ao teto, e a resposta "
        "informa o que foi efetivamente usado.",
    )
    webhook_url: str | None = None


class SnippetJobRequest(BaseModel):
    """Document inline code. Used by the VS Code extension."""

    job_type: Literal["document_snippet"] = "document_snippet"
    path: str = Field(description="Caminho do arquivo, usado para detectar a linguagem")
    content: str = Field(min_length=1, max_length=1_000_000)
    project_id: uuid.UUID | None = None
    output_language: str = Field(default="pt-BR")
    depth: GenerationDepth | None = Field(
        default=None,
        description="Profundidade da analise. Omitido usa o maximo do plano. "
        "Pedir acima do plano nao da erro: e reduzido ao teto, e a resposta "
        "informa o que foi efetivamente usado.",
    )
    webhook_url: str | None = None


JobRequest = RepositoryJobRequest | SnippetJobRequest


class JobResponse(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    progress_percent: int
    progress_message: str | None
    attempts: int
    project_id: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    document_count: int = 0
    depth: str = Field(description="Profundidade efetivamente aplicada a este job.")

    source: str | None = Field(
        default=None,
        description="O que foi analisado: a URL do repositorio ou o nome do arquivo. "
        "Sem isto, uma lista de jobs so mostra datas e a pessoa nao reconhece qual e qual.",
    )


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


# -------------------------------------------------------------- documentos


class DocumentSummaryResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    path: str
    language: str
    summary: str | None
    symbol_count: int
    finding_count: int
    depth: str
    created_at: datetime


class FindingResponse(BaseModel):
    id: uuid.UUID
    category: str
    severity: str
    title: str
    detail: str
    suggestion: str | None
    symbol_name: str | None
    line_start: int | None
    line_end: int | None
    confidence: float


class DocumentResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    path: str
    language: str
    summary: str | None
    symbols: list[SymbolDoc]
    findings: list[FindingResponse]
    findings_locked: bool = Field(
        default=False,
        description="True quando existem pontos de melhoria, mas o plano atual nao os libera.",
    )
    depth: str = Field(description="Profundidade que gerou este documento.")
    created_at: datetime


# ------------------------------------------------------------------- meta


class LanguageResponse(BaseModel):
    name: str
    display_name: str
    extensions: list[str]


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


__all__ = [name for name in dir() if name.endswith(("Request", "Response", "Info", "Draft"))]


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=16)
    new_password: str
