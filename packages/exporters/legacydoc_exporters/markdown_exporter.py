"""Exportador Markdown."""

from __future__ import annotations

from legacydoc_core.domain import FileDocumentation, FindingDraft, SymbolDoc

from legacydoc_exporters.base import DocumentExporter, ExporterFactory

_SEVERITY_LABEL = {
    "critical": "Critico",
    "high": "Alto",
    "medium": "Medio",
    "low": "Baixo",
    "info": "Informativo",
}

_CATEGORY_LABEL = {
    "complexity": "Complexidade",
    "maintainability": "Manutenibilidade",
    "correctness": "Correcao",
    "security": "Seguranca",
    "performance": "Desempenho",
    "testing": "Testes",
    "documentation": "Documentacao",
}


class MarkdownExporter(DocumentExporter):
    format_name = "markdown"
    media_type = "text/markdown; charset=utf-8"
    extension = ".md"

    def render(self, documentation: FileDocumentation, *, include_findings: bool) -> bytes:
        parts: list[str] = [
            f"# `{documentation.path}`\n",
            f"> Linguagem: **{documentation.language}** · "
            f"Simbolos documentados: **{len(documentation.symbols)}**\n",
        ]

        if documentation.summary:
            parts.append(f"\n{documentation.summary}\n")

        if documentation.symbols:
            parts.append("\n## Indice\n")
            for symbol in documentation.symbols:
                parts.append(f"- [`{symbol.name}`](#{_anchor(symbol.name)}) — {symbol.summary}")
            parts.append("")

        if include_findings and documentation.findings:
            parts.append(_render_findings(documentation.findings))

        for symbol in documentation.symbols:
            parts.append(_render_symbol(symbol))

        return "\n".join(parts).encode("utf-8")


def _render_symbol(symbol: SymbolDoc) -> str:
    lines = [f"\n---\n\n## `{symbol.name}`\n"]

    location = f"linhas {symbol.line_start}–{symbol.line_end}" if symbol.line_end else ""
    meta = " · ".join(
        part
        for part in (
            symbol.kind,
            f"em `{symbol.parent}`" if symbol.parent else "",
            location,
            f"complexidade ~{symbol.complexity_estimate}" if symbol.complexity_estimate else "",
        )
        if part
    )

    if meta:
        lines.append(f"*{meta}*\n")

    lines.append(f"> {symbol.summary}\n")

    if symbol.signature:
        lines.append(f"```{symbol.language}\n{symbol.signature}\n```\n")

    if symbol.parameters:
        lines.append("### Parametros\n")
        lines.append("| Nome | Tipo | Descricao |")
        lines.append("| :--- | :--- | :--- |")

        for parameter in symbol.parameters:
            description = parameter.description or "—"
            optional = " *(opcional)*" if parameter.optional else ""
            lines.append(
                f"| `{parameter.name}`{optional} | `{parameter.type or '—'}` | {description} |"
            )

        lines.append("")

    if symbol.return_type or symbol.return_description:
        lines.append("### Retorno\n")
        lines.append(f"- **Tipo:** `{symbol.return_type or '—'}`")

        if symbol.return_description:
            lines.append(f"- {symbol.return_description}")

        lines.append("")

    if symbol.raises:
        lines.append("### Excecoes\n")
        lines.extend(f"- `{item}`" for item in symbol.raises)
        lines.append("")

    if symbol.side_effects:
        lines.append("### Efeitos colaterais\n")
        lines.extend(f"- {item}" for item in symbol.side_effects)
        lines.append("")

    lines.append("### Descricao\n")
    lines.append(f"{symbol.description}\n")

    return "\n".join(lines)


def _render_findings(findings: list[FindingDraft]) -> str:
    lines = ["\n## Pontos de melhoria\n"]
    lines.append("| Severidade | Categoria | Simbolo | Ponto |")
    lines.append("| :--- | :--- | :--- | :--- |")

    for finding in findings:
        severity = _SEVERITY_LABEL.get(str(finding.severity), str(finding.severity))
        category = _CATEGORY_LABEL.get(str(finding.category), str(finding.category))
        symbol = f"`{finding.symbol_name}`" if finding.symbol_name else "—"
        lines.append(f"| {severity} | {category} | {symbol} | {finding.title} |")

    lines.append("")

    for finding in findings:
        severity = _SEVERITY_LABEL.get(str(finding.severity), str(finding.severity))
        lines.append(f"\n### {finding.title}\n")

        location = (
            f" · linhas {finding.line_start}–{finding.line_end}" if finding.line_start else ""
        )
        lines.append(
            f"*{severity} · "
            f"{_CATEGORY_LABEL.get(str(finding.category), str(finding.category))}"
            f"{location} · confianca {finding.confidence:.0%}*\n"
        )
        lines.append(f"{finding.detail}\n")

        if finding.suggestion:
            lines.append(f"**Sugestao:** {finding.suggestion}\n")

    return "\n".join(lines)


def _anchor(name: str) -> str:
    return "".join(char for char in name.lower() if char.isalnum() or char in "-_")


ExporterFactory.register(MarkdownExporter, "md")
