# main.py
import os
import json
from dotenv import load_dotenv
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from tools.github_loader import load_cpp_from_github
from agents.reader import run_reader_agent
from agents.writer import run_writer_agent
from agents.verifier import run_verifier_agent
from core.schemas import FileDocumentation
from tools.pdf_generator import export_doc_to_pdf

USE_MANUAL_MODE = False

load_dotenv()

class GraphState(TypedDict):
    code: str
    context: str
    documentation: Optional[FileDocumentation]
    reviewer_feedback: str
    attempts: int

def split_code(code: str, lines_per_chunk: int = 250):
    lines = code.split('\n')
    for i in range(0, len(lines), lines_per_chunk):
        yield '\n'.join(lines[i:i + lines_per_chunk])

def node_reader(state: GraphState):
    if USE_MANUAL_MODE:
        print("\n" + "=" * 50)
        print("🔍 [MODO MANUAL] - AGENTE: READER")
        print("COPIE O CÓDIGO ABAIXO PARA O SEU GPT 'READER':")
        print("-" * 30)
        print(state["code"])
        print("-" * 30)

        status = input("\nO Reader aprovou o contexto? (s/n): ").lower()
        if status == 'n':
            queries = input("Quais dúvidas o Reader gerou? (Cole aqui): ")
            print(f"\n💡 [Ação]: Leve as dúvidas ao GPT 'SEARCHER' e cole a resposta abaixo.")
            contexto = input("Resposta do SEARCHER: ")
        else:
            contexto = "Código autossuficiente."

        return {"context": contexto}
    else:
        print("\n" + "=" * 50)
        print("🔍 [API] - AGENTE: READER")

        result = run_reader_agent(state["code"])

        print(f"\n💬 Reader diz: {result.user_facing_message}")

        novo_contexto = state["context"]
        if not result.ready_to_write:
            novo_contexto += f"\n\n[Reader queries pending search]: {result.queries}"
        else:
            novo_contexto += "\n\n[Status]: The code is self-sufficient.."

        return {"context": novo_contexto}


def node_writer(state: GraphState):
    if USE_MANUAL_MODE:
        print("\n" + "=" * 50)
        print("✍️ [MODO MANUAL] - AGENTE: WRITER")
        if state.get("reviewer_feedback") and state["reviewer_feedback"] != "APPROVED":
            print(f"❌ REVISÃO SOLICITADA PELO VERIFIER:\n{state['reviewer_feedback']}")

        print(f"\nCONTEXTO PARA O WRITER: {state['context']}")

        print("\nAGUARDANDO O JSON DO GPT 'WRITER'...")
        print("Cole o JSON abaixo. Quando terminar, digite 'FIM' em uma nova linha e aperte Enter:")

        linhas = []
        while True:
            linha = input()
            if linha.strip().upper() == 'FIM':
                break
            linhas.append(linha)

        raw_json = "\n".join(linhas)

        try:
            doc_dict = json.loads(raw_json)
            return {"documentation": doc_dict, "attempts": state.get("attempts", 0) + 1}
        except Exception as e:
            print(f"⚠️ Erro de formato no JSON: {e}. O sistema salvará como texto bruto.")
            return {"documentation": raw_json, "attempts": state.get("attempts", 0) + 1}
    else:
        print("\n" + "=" * 50)
        print("✍️ [API] - AGENTE: WRITER")

        full_code = state["code"]
        current_context = state["context"]
        all_functions = []

        chunks = list(split_code(full_code, lines_per_chunk=50))
        total_chunks = len(chunks)

        for idx, chunk in enumerate(chunks):
            print(f"📦 Processed chunk {idx + 1} de {total_chunks}...")

            try:
                result = run_writer_agent(chunk, current_context)

                if result and hasattr(result, "functions"):
                    all_functions.extend(result.functions)
                else:
                    print(f"⚠️ Chunk {idx + 1} não retornou funções.")

            except Exception as e:
                print(f"⚠️ ERROR in chunk {idx + 1}: {e}")

        final_doc = FileDocumentation(functions=all_functions)

        print(f"✅ Writer finalizou com {len(all_functions)} funções documentadas.")

        return {
            "documentation": final_doc,
            "attempts": state.get("attempts", 0) + 1
        }


def node_verifier(state: GraphState):
    if USE_MANUAL_MODE:
        print("\n" + "=" * 50)
        print("⚖️ [MODO MANUAL] - AGENTE: VERIFIER")
        print("SUBMETA A DOCUMENTAÇÃO E O CÓDIGO AO GPT 'VERIFIER'.")

        aprovado = input("\nFoi aprovado? (s/n): ").lower()
        if aprovado == 's':
            return {"reviewer_feedback": "APPROVED"}
        else:
            feedback = input("Cole o feedback de reprovação: ")
            return {"reviewer_feedback": feedback}
    else:
        print("\n" + "=" * 50)
        print("⚖️ [API] - AGENTE: VERIFIER")

        result = run_verifier_agent(state["code"], state["documentation"])

        print(f"\n💬 Verifier diz: {result.feedback_message}")

        if result.approved:
            feedback = "APPROVED"
        else:
            feedback = f"Technical Audit: {result.technical_audit}\nHRBP Question: {result.feedback_message}"

        return {"reviewer_feedback": feedback}

def decide_next_step(state: GraphState):
    if state["reviewer_feedback"] == "APPROVED":
        return END
    return "writer" if state["attempts"] < 3 else END

workflow = StateGraph(GraphState)

workflow.add_node("reader", node_reader)
workflow.add_node("writer", node_writer)
workflow.add_node("verifier", node_verifier)

workflow.set_entry_point("reader")
workflow.add_edge("reader", "writer")
workflow.add_edge("writer", "verifier")

workflow.add_conditional_edges(
    "verifier",
    decide_next_step,
    {"writer": "writer", END: END}
)

app = workflow.compile()


def process_single_file(github_url: str, requested_file_path: str):
    print(f"🚀 Downloading : {github_url}")
    repo_files = load_cpp_from_github(github_url, target_dir="./tmp_repo")

    if not repo_files:
        raise ValueError("Empty repository or clone failed.")

    print(f"📄 Files C/C++ concentrates: {len(repo_files)}")
    for path in list(repo_files.keys())[:10]:
        print(f" - {path}")

    if requested_file_path == "TESTE":
        available_files = list(repo_files.keys())

        if not available_files:
            raise ValueError("❌ No C/C++ files found in the repository..")

        requested_file_path = available_files[0]
        print(f"🧪 TESTE mode: using first available file: {requested_file_path}")

    selected_file_content = repo_files[requested_file_path]

    initial_state = {
        "code": selected_file_content,
        "context": f"Path: {requested_file_path}",
        "documentation": None,
        "reviewer_feedback": "",
        "attempts": 0
    }

    final_result = app.invoke(initial_state)
    doc = final_result.get("documentation")

    if doc:
        if hasattr(doc, "model_dump"):
            doc_dict = doc.model_dump()
        elif isinstance(doc, dict):
            doc_dict = doc
        else:
            doc_dict = {"functions": []}

        safe_filename = os.path.basename(requested_file_path)
        safe_filename = safe_filename.replace(".cpp", "").replace(".hpp", "").replace(".h", "")

        os.makedirs("pdfs", exist_ok=True)
        pdf_filename = f"Doc_WaveCast_{safe_filename}.pdf"
        pdf_path = os.path.join("pdfs", pdf_filename)

        export_doc_to_pdf(
            doc_data=doc_dict,
            file_name=requested_file_path,
            output_path=pdf_path
        )

        os.makedirs("data", exist_ok=True)
        json_filename = f"{safe_filename}.json"
        json_path = os.path.join("data", json_filename)

        array_de_funcoes = doc_dict.get("functions", [])

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(array_de_funcoes, f, indent=2, ensure_ascii=False)

        return {
            "file": requested_file_path,
            "status": "success",
            "pdf_filename": pdf_filename,
            "json_filename": json_filename,
            "pdf_url": f"http://localhost:8000/pdfs/{pdf_filename}",
            "json_url": f"http://localhost:8000/data/{json_filename}",
            "documentation": array_de_funcoes
        }
    else:
        raise RuntimeError("Failed to generate documentation.")


if __name__ == "__main__":
    url_teste = "https://github.com/dosbox-staging/dosbox-staging.git"
    print("🚀 Starting test in the terminal (Getting file [3])...")
    try:
        resultado = process_single_file(url_teste, "TESTE")
        print("\n✅ SUCCESS! PDF saved and JSON returned.:")
        print(json.dumps(resultado["documentation"], indent=2))
    except Exception as e:
        print(f"❌ Erro: {e}")
