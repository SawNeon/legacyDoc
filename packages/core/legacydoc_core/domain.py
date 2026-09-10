"""Domain objects exchanged between parsing, agents and exporters.

They are Pydantic models because they double as the JSON Schema for structured
LLM output: one definition is both the agent contract and the response validator.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from legacydoc_core.models import FindingCategory, Severity


class Parameter(BaseModel):
    name: str = Field(description="Nome do parametro exatamente como no codigo")
    type: str | None = Field(default=None, description="Tipo declarado, se a linguagem tiver")
    description: str | None = Field(default=None, description="O que o parametro representa")
    optional: bool = Field(default=False)
    default: str | None = Field(default=None)


class SymbolDoc(BaseModel):
    """Documentation for one symbol: function, method, class, struct or interface."""

    name: str
    kind: str = Field(default="function", description="function, method, class, struct, interface")
    signature: str = Field(description="Assinatura original, copiada do codigo")
    language: str
    line_start: int = Field(default=0, ge=0)
    line_end: int = Field(default=0, ge=0)

    summary: str = Field(description="Uma linha, no idioma pedido")
    description: str = Field(description="Explicacao em Situacao / Acao / Impacto")

    parameters: list[Parameter] = Field(default_factory=list)
    return_type: str | None = None
    return_description: str | None = None
    raises: list[str] = Field(
        default_factory=list,
        description="Somente excecoes lancadas explicitamente no codigo",
    )
    side_effects: list[str] = Field(
        default_factory=list,
        description="I/O, estado global, rede, banco. Vazio se a funcao e pura",
    )
    complexity_estimate: int | None = Field(
        default=None,
        description="Complexidade ciclomatica aproximada, calculada pelo parser",
    )

    parent: str | None = Field(default=None, description="Classe ou modulo que contem o simbolo")


class FindingDraft(BaseModel):
    """An improvement finding before it becomes a database row."""

    category: FindingCategory
    severity: Severity
    title: str = Field(max_length=300)
    detail: str
    suggestion: str | None = None
    symbol_name: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class FileDocumentation(BaseModel):
    """Complete result for a single file."""

    path: str
    language: str
    summary: str = ""
    symbols: list[SymbolDoc] = Field(default_factory=list)
    findings: list[FindingDraft] = Field(default_factory=list)


# Modelos enxutos: quanto menor o schema, menor a chance do LLM alucinar campo.


class WriterOutput(BaseModel):
    symbols: list[SymbolDoc] = Field(default_factory=list)


class ImproverOutput(BaseModel):
    findings: list[FindingDraft] = Field(default_factory=list)


class VerifierOutput(BaseModel):
    approved: bool = Field(description="True se a documentacao e fiel ao codigo")
    rejected_symbols: list[str] = Field(
        default_factory=list,
        description="Nomes dos simbolos com problema; vazio se aprovado",
    )
    audit_notes: str = Field(description="Auditoria tecnica, em ingles, para o proximo passo")
    feedback_message: str = Field(description="Mensagem para o usuario, no idioma do projeto")


class SummarizerOutput(BaseModel):
    summary: str = Field(description="Resumo do arquivo em 2 a 4 frases")
