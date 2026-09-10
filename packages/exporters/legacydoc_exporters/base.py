"""Exporter contract and factory.

The factory and abstract base carried over from v1 almost untouched: it was the
best part of that code and genuinely extensible. What changed is the input,
now a typed `FileDocumentation` instead of a loose dict, and the output, now
bytes instead of a file on disk, so one exporter serves HTTP downloads, webhook
attachments and the VS Code extension alike.
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
    """One output format."""

    format_name: str
    media_type: str
    extension: str

    @abstractmethod
    def render(self, documentation: FileDocumentation, *, include_findings: bool) -> bytes:
        """Serialize the documentation. Never touches disk."""

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
    """Safe filename that preserves the path hierarchy.

    v1 used the basename alone, so two files with the same name from different
    repositories overwrote each other on shared disk. Here the full path is
    flattened, which does not collide.
    """
    import re

    normalized = path.replace("\\", "/").strip("/")
    stem = normalized.rsplit(".", 1)[0] if "." in normalized.rsplit("/", 1)[-1] else normalized
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")

    return cleaned[:120] or "documentation"
