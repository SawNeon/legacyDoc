# tools/pdf_generator.py
from fpdf import FPDF
import json

class LegacyDocPDF(FPDF):
    def header(self):

        self.set_font("helvetica", "B", 16)
        self.set_text_color(0, 102, 204)
        self.cell(0, 10, "Legacy Doc - Documentação Técnica", border=False, ln=True, align="C")
        self.set_draw_color(0, 102, 204)
        self.line(10, 22, 200, 22)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def export_doc_to_pdf(doc_data: dict, file_name: str, output_path: str = "documentacao.pdf"):

    pdf = LegacyDocPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    def add_section_title(title):
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 10, title, ln=True)
        pdf.ln(2)

    def add_body_text(text):
        pdf.set_font("helvetica", "", 11)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 6, text)
        pdf.ln(5)

    def add_code_block(text):
        pdf.set_font("courier", "", 10)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(0, 5, text)
        pdf.ln(3)

    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, f"Module: {file_name}", ln=True)
    pdf.ln(5)

    if "summary" in doc_data:
        add_section_title("Summary:")
        add_body_text(str(doc_data["summary"]))

    if "constants" in doc_data and isinstance(doc_data["constants"], list) and len(doc_data["constants"]) > 0:
        add_section_title("Constants:")
        for const in doc_data["constants"]:
            name = const.get("name", "N/A")
            ctype = const.get("type", "N/A")
            val = const.get("value", "N/A")
            desc = const.get("summary", const.get("description", ""))

            pdf.set_font("helvetica", "B", 11)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 6, f"- {name}", ln=True)

            add_code_block(f"Type: {ctype}\nValue: {val}")
            if desc:
                add_body_text(desc)

    if "functions" in doc_data and isinstance(doc_data["functions"], list) and len(doc_data["functions"]) > 0:
        add_section_title("Functions:")

        for func in doc_data["functions"]:
            name = func.get("name", "N/A")
            sig = func.get("signature", "")

            pdf.set_font("helvetica", "B", 12)
            pdf.set_text_color(0, 102, 204)  # Azul
            pdf.cell(0, 8, f"Function: {name}", ln=True)

            if sig:
                add_code_block(sig)

            if "summary" in func:
                add_body_text(func["summary"])

            if "description" in func:
                add_body_text(f"Details: {func['description']}")

            if "args" in func and func["args"]:
                pdf.set_font("helvetica", "B", 10)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(0, 6, "Parameters:", ln=True)
                for arg in func["args"]:
                    aname = arg.get("name", "N/A")
                    atype = arg.get("type", "N/A")
                    adesc = arg.get("description", "")
                    add_body_text(f"  - {aname} ({atype}): {adesc}")

            if "returns" in func:
                ret = func["returns"]
                pdf.set_font("helvetica", "B", 10)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(0, 6, "Returns:", ln=True)
                if isinstance(ret, dict):
                    add_body_text(f"  Type: {ret.get('type', 'N/A')}\n  Description: {ret.get('description', '')}")
                else:
                    add_body_text(f"  {str(ret)}")

            pdf.ln(5)

    pdf.output(output_path)
    print(f"\n📑 [PDF Generator]: Successful ! PDF save pdf in: '{output_path}'")