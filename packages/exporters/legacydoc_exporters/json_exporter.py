"""JSON exporter."""

from __future__ import annotations

import json

from legacydoc_core.domain import FileDocumentation

from legacydoc_exporters.base import DocumentExporter, ExporterFactory


class JsonExporter(DocumentExporter):
    format_name = "json"
    media_type = "application/json"
    extension = ".json"

    def render(self, documentation: FileDocumentation, *, include_findings: bool) -> bytes:
        payload = documentation.model_dump(mode="json")

        if not include_findings:
            payload["findings"] = []

        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


ExporterFactory.register(JsonExporter)
