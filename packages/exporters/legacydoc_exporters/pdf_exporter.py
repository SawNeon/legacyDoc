"""PDF exporter.

Fixes three defects in the v1 generator: it read field names that never existed
in the schema, so the return type never reached the PDF; it did not handle text
outside latin-1, so a single non-Western identifier broke generation entirely;
and it had no wrapping for long identifiers, which overflowed the margin.
"""

from __future__ import annotations

from fpdf import FPDF
from legacydoc_core.domain import FileDocumentation, SymbolDoc

from legacydoc_exporters.base import DocumentExporter, ExporterFactory

_ACCENT = (0, 102, 204)
_TEXT = (35, 35, 35)
_MUTED = (120, 120, 120)

_SEVERITY_COLOR = {
    "critical": (176, 0, 32),
    "high": (198, 76, 0),
    "medium": (150, 120, 0),
    "low": (80, 110, 80),
    "info": (100, 100, 100),
}


def _latin1_safe(text: str) -> str:
    """Make text printable by the fpdf2 core fonts.

    Replaces anything outside latin-1 rather than raising. Real CJK support
    would require embedding a Unicode TTF, adding roughly 10 MB to the package;
    until then degrading beats failing.
    """
    return text.encode("latin-1", errors="replace").decode("latin-1")


class _LegacyDocPDF(FPDF):
    def __init__(self, title: str) -> None:
        super().__init__()
        self._doc_title = _latin1_safe(title)

    def header(self) -> None:
        self.set_font("helvetica", "B", 13)
        self.set_text_color(*_ACCENT)
        self.cell(0, 8, "Legacy Doc", align="L")
        self.set_font("helvetica", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(0, 8, self._doc_title, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_ACCENT)
        self.line(10, 20, 200, 20)
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(*_MUTED)
        self.cell(0, 10, f"Pagina {self.page_no()}", align="C")


class PdfExporter(DocumentExporter):
    format_name = "pdf"
    media_type = "application/pdf"
    extension = ".pdf"

    def render(self, documentation: FileDocumentation, *, include_findings: bool) -> bytes:
        pdf = _LegacyDocPDF(documentation.path)
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_page()

        self._title_block(pdf, documentation)

        if include_findings and documentation.findings:
            self._findings_section(pdf, documentation)

        if documentation.symbols:
            self._heading(pdf, "Simbolos documentados")

            for symbol in documentation.symbols:
                self._symbol_block(pdf, symbol)

        output = pdf.output()

        return bytes(output)

    # ------------------------------------------------------------- blocos

    def _title_block(self, pdf: FPDF, documentation: FileDocumentation) -> None:
        pdf.set_font("helvetica", "B", 16)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 8, _latin1_safe(documentation.path), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(
            0,
            5,
            _latin1_safe(
                f"Linguagem: {documentation.language}  |  "
                f"Simbolos: {len(documentation.symbols)}  |  "
                f"Pontos de melhoria: {len(documentation.findings)}"
            ),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(4)

        if documentation.summary:
            pdf.set_font("helvetica", "", 11)
            pdf.set_text_color(*_TEXT)
            pdf.multi_cell(0, 6, _latin1_safe(documentation.summary), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

    def _findings_section(self, pdf: FPDF, documentation: FileDocumentation) -> None:
        self._heading(pdf, "Pontos de melhoria")

        for finding in documentation.findings:
            severity = str(finding.severity)

            pdf.set_font("helvetica", "B", 10)
            pdf.set_text_color(*_SEVERITY_COLOR.get(severity, _TEXT))
            pdf.multi_cell(
                0,
                5,
                _latin1_safe(f"[{severity.upper()}] {finding.title}"),
                new_x="LMARGIN",
                new_y="NEXT",
            )

            pdf.set_font("helvetica", "I", 8)
            pdf.set_text_color(*_MUTED)
            location = (
                f" | linhas {finding.line_start}-{finding.line_end}" if finding.line_start else ""
            )
            pdf.multi_cell(
                0,
                4,
                _latin1_safe(
                    f"{finding.category}"
                    f"{f' | {finding.symbol_name}' if finding.symbol_name else ''}"
                    f"{location} | confianca {finding.confidence:.0%}"
                ),
                new_x="LMARGIN",
                new_y="NEXT",
            )

            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(*_TEXT)
            pdf.multi_cell(0, 5, _latin1_safe(finding.detail), new_x="LMARGIN", new_y="NEXT")

            if finding.suggestion:
                pdf.set_font("helvetica", "I", 10)
                pdf.multi_cell(
                    0,
                    5,
                    _latin1_safe(f"Sugestao: {finding.suggestion}"),
                    new_x="LMARGIN",
                    new_y="NEXT",
                )

            pdf.ln(3)

        pdf.ln(2)

    def _symbol_block(self, pdf: FPDF, symbol: SymbolDoc) -> None:
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(*_ACCENT)
        pdf.multi_cell(0, 6, _latin1_safe(symbol.name), new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(*_MUTED)
        meta = [symbol.kind]

        if symbol.parent:
            meta.append(f"em {symbol.parent}")
        if symbol.line_end:
            meta.append(f"linhas {symbol.line_start}-{symbol.line_end}")
        if symbol.complexity_estimate:
            meta.append(f"complexidade ~{symbol.complexity_estimate}")

        pdf.multi_cell(0, 4, _latin1_safe(" | ".join(meta)), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        if symbol.signature:
            pdf.set_font("courier", "", 8)
            pdf.set_text_color(20, 20, 20)
            # wrapmode=CHAR keeps a space-less signature from overflowing the margin.
            pdf.multi_cell(
                0, 4, _latin1_safe(symbol.signature), wrapmode="CHAR", new_x="LMARGIN", new_y="NEXT"
            )
            pdf.ln(1)

        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(*_TEXT)
        pdf.multi_cell(0, 5, _latin1_safe(symbol.summary), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        if symbol.parameters:
            pdf.set_font("helvetica", "B", 9)
            pdf.cell(0, 5, "Parametros:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 9)

            for parameter in symbol.parameters:
                description = f": {parameter.description}" if parameter.description else ""
                pdf.multi_cell(
                    0,
                    4,
                    _latin1_safe(
                        f"   - {parameter.name} ({parameter.type or 'nao declarado'}){description}"
                    ),
                    new_x="LMARGIN",
                    new_y="NEXT",
                )

        # v1 read a key absent from the schema, so the return never reached the
        # PDF. These two fields are the correct ones.
        if symbol.return_type or symbol.return_description:
            pdf.set_font("helvetica", "B", 9)
            pdf.cell(0, 5, "Retorno:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 9)
            pdf.multi_cell(
                0,
                4,
                _latin1_safe(
                    f"   {symbol.return_type or 'nao declarado'}"
                    f"{f' - {symbol.return_description}' if symbol.return_description else ''}"
                ),
                new_x="LMARGIN",
                new_y="NEXT",
            )

        if symbol.raises:
            pdf.set_font("helvetica", "B", 9)
            pdf.cell(0, 5, "Excecoes:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 9)
            for item in symbol.raises:
                pdf.multi_cell(0, 4, _latin1_safe(f"   - {item}"), new_x="LMARGIN", new_y="NEXT")

        if symbol.side_effects:
            pdf.set_font("helvetica", "B", 9)
            pdf.cell(0, 5, "Efeitos colaterais:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 9)
            for item in symbol.side_effects:
                pdf.multi_cell(0, 4, _latin1_safe(f"   - {item}"), new_x="LMARGIN", new_y="NEXT")

        pdf.ln(1)
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(*_TEXT)
        pdf.multi_cell(0, 5, _latin1_safe(symbol.description), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

    def _heading(self, pdf: FPDF, text: str) -> None:
        pdf.set_font("helvetica", "B", 13)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 7, _latin1_safe(text), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)


ExporterFactory.register(PdfExporter)
