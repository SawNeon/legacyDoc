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
from core.schemas import DocstringSchema
from tools.pdf_generator import export_doc_to_pdf

USE_MANUAL_MODE = True

load_dotenv()

class GraphState(TypedDict):
    code: str
    context: str
    documentation: Optional[DocstringSchema]
    reviewer_feedback: str
    attempts: int


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
        # CAMPO PARA API (Comentado/Desativado por enquanto)
        # result = run_reader_agent(state["code"])
        # return {"context": result.context}
        pass


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
        pass


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
        # CAMPO PARA API
        # result = run_verifier_agent(state["code"], state["documentation"])
        # return {"reviewer_feedback": "APPROVED" if result.approved else result.reason}
        pass


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


if __name__ == "__main__":
    github_url = "https://github.com/dosbox-staging/dosbox-staging.git"

    print("🚀 Iniciando Workflow WaveCast...\n")

    repo_files = load_cpp_from_github(github_url, target_dir="./tmp_repo")

    if repo_files:
        first_file_path = list(repo_files.keys())[3]
        first_file_content = repo_files[first_file_path]

        print(f"\n📄 Processando arquivo: {first_file_path}")

        initial_state = {
            "code": first_file_content,
            "context": f"Path: {first_file_path}",
            "documentation": None,
            "reviewer_feedback": "",
            "attempts": 0
        }

        final_result = app.invoke(initial_state)

        print("\n" + "=" * 60)
        print(f" ✅ RESULTADO FINAL DA DOCUMENTAÇÃO: {first_file_path} ")
        print("=" * 60)

        doc = final_result.get("documentation")

        if doc:
            if hasattr(doc, "model_dump_json"):
                print(doc.model_dump_json(indent=2))
                doc_dict = json.loads(doc.model_dump_json())
            elif isinstance(doc, dict):
                print(json.dumps(doc, indent=2, ensure_ascii=False))
                doc_dict = doc
            else:
                print(doc)
                doc_dict = {"description": str(doc)}


            pdf_filename = f"Doc_{os.path.basename(first_file_path)}.pdf"
            export_doc_to_pdf(doc_data=doc_dict, file_name=first_file_path, output_path=pdf_filename)

        else:
                print(doc)

    else:
        print("The C++ file was not found in the directory..")

