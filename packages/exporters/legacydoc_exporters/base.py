"""Contrato e fabrica de exportadores.

O padrao Factory + ABC veio da v1 praticamente intacto: era a melhor parte
daquele codigo, extensivel de verdade. O que mudou e a entrada, que agora e o
modelo tipado `FileDocumentation` em vez de um dict solto, e a saida, que sao
bytes em vez de um arquivo escrito em disco - assim o mesmo exportador serve
para download HTTP, para anexo de webhook e para a extensao do VS Code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from legacydoc_core.domain import FileDocumentation
from legacydoc_core.errors import ValidationError


@dataclass(frozen=True)
class ExportResult:
    content: bytes
    media_type: str
    suggested_filename: str


class DocumentExporter(ABC):
    """Um formato de saida."""

    format_name: str
    media_type: str
    extension: str

    @abstractmethod
    def render(self, documentation: FileDocumentation, *, include_findings: bool) -> bytes:
        """Serializa a documentacao. Nao toca em disco."""

    def export(
        self,
        documentation: FileDocumentation,
        *,
        include_findings: bool = True,
        filename_stem: str | None = None,
    ) -> ExportResult:
        stem = filename_stem or safe_stem(documentation.path)

        return ExportResult(
            content=self.render(documentation, include_findings=include_findings),
            media_type=self.media_type,
            suggested_filename=f"{stem}{self.extension}",
        )


class ExporterFactory:
    _exporters: dict[str, type[DocumentExporter]] = {}

    @classmethod
    def register(cls, exporter: type[DocumentExporter], *aliases: str) -> type[DocumentExporter]:
        cls._exporters[exporter.format_name] = exporter

        for alias in aliases:
            cls._exporters[alias] = exporter

        return exporter

    @classmethod
    def get(cls, output_format: str) -> DocumentExporter:
        exporter = cls._exporters.get(output_format.lower().strip())

        if exporter is None:
            raise ValidationError(
                f"Formato de exportacao invalido: {output_format}. "
                f"Suportados: {', '.join(sorted(set(cls._exporters)))}"
            )

        return exporter()

    @classmethod
    def available_formats(cls) -> list[str]:
        return sorted({exporter.format_name for exporter in cls._exporters.values()})


def safe_stem(path: str) -> str:
    """Nome de arquivo seguro, preservando a hierarquia do caminho.

    A v1 usava so o basename, entao dois `main.cpp` de repositorios diferentes
    se sobrescreviam no disco compartilhado. Aqui `src/net/main.cpp` vira
    `src_net_main`, que nao colide.
    """
    import re

    normalized = path.replace("\\", "/").strip("/")
    stem = normalized.rsplit(".", 1)[0] if "." in normalized.rsplit("/", 1)[-1] else normalized
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")

    return cleaned[:120] or "documentacao"
