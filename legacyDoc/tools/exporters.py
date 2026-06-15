import os
from pathlib import Path
from abc import ABC, abstractmethod
from tools.pdf_generator import export_doc_to_pdf


class DocumentExporter(ABC):
    @abstractmethod
    def export(self, doc_data: dict, safe_filename: str, output_dir: str) -> str:
        pass


class PdfExporter(DocumentExporter):
    def export(self, doc_data: dict, safe_filename: str, output_dir: str) -> str:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        pdf_filename = f"Doc_LegacyDoc_{safe_filename}.pdf"
        pdf_path = output_path / pdf_filename

        export_doc_to_pdf(
            doc_data=doc_data,
            file_name=safe_filename,
            output_path=str(pdf_path)
        )

        if not pdf_path.exists():
            raise RuntimeError(f"The PDF was not found after generation: {pdf_path.resolve()}")

        print(f"PDF created in: {pdf_path.resolve()}")

        return pdf_filename


class MarkdownExporter(DocumentExporter):
    def export(self, doc_data: dict, safe_filename: str, output_dir: str) -> str:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        md_filename = f"Doc_LegacyDoc_{safe_filename}.md"
        md_path = output_path / md_filename

        functions = doc_data.get("functions", [])

        md_content = f"# 📄 Documentação de Código: `{safe_filename}`\n\n"
        md_content += f"> Documentação gerada automaticamente para o módulo **{safe_filename}**.\n\n"

        if functions:
            md_content += "## 📑 Índice de Funções\n\n"

            for func in functions:
                func_name = func.get("name", "desconhecida")
                anchor = func_name.lower().replace(" ", "-")
                md_content += f"- [{func_name}](#-função-{anchor})\n"

            md_content += "\n---\n\n"

        for func in functions:
            name = func.get("name", "Desconhecida")
            ret_type = func.get("return_type", "void")
            summary = func.get("summary", "Sem resumo disponível.")
            desc = func.get("description", "Sem descrição detalhada.")
            args = func.get("args", [])
            raises = func.get("raises", [])

            md_content += f"## 🛠 Função: `{name}`\n\n"
            md_content += f"> **Resumo:** {summary}\n\n"

            signature = func.get("signature")

            if not signature:
                args_str = ", ".join(
                    f"{arg.get('type', '')} {arg.get('name', '')}".strip()
                    for arg in args
                )
                signature = f"{ret_type} {name}({args_str});"

            md_content += "### 💻 Assinatura\n\n"
            md_content += f"```cpp\n{signature}\n```\n\n"

            if args:
                md_content += "### 📥 Parâmetros\n\n"
                md_content += "| Tipo | Nome |\n"
                md_content += "| :--- | :--- |\n"

                for arg in args:
                    arg_type = arg.get("type", "-")
                    arg_name = arg.get("name", "-")
                    md_content += f"| `{arg_type}` | **{arg_name}** |\n"

                md_content += "\n"

            md_content += "### 📤 Retorno\n\n"
            md_content += f"- **Tipo:** `{ret_type}`\n\n"

            if raises:
                md_content += "### ⚠️ Exceções / Throws\n\n"

                for exc in raises:
                    md_content += f"- `{exc}`\n"

                md_content += "\n"

            md_content += "### 📖 Descrição Detalhada\n\n"
            md_content += f"{desc}\n\n"

            md_content += "---\n\n"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        if not md_path.exists():
            raise RuntimeError(f"The Markdown was not found after generation: {md_path.resolve()}")

        print(f"Markdown created in: {md_path.resolve()}")

        return md_filename


class ExporterFactory:
    _exporters = {
        "pdf": PdfExporter,
        "markdown": MarkdownExporter,
        "md": MarkdownExporter,
    }

    @classmethod
    def get_exporter(cls, output_format: str) -> DocumentExporter:
        normalized_format = output_format.lower().strip()

        exporter_class = cls._exporters.get(normalized_format)

        if not exporter_class:
            supported = ", ".join(cls._exporters.keys())
            raise ValueError(
                f"Invalid export format: {output_format}. "
                f"Supported formats: {supported}"
            )

        return exporter_class()
