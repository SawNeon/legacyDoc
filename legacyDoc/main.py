# main.py
from sys import path

from tools.github_loader import load_cpp_from_github
from dotenv import load_dotenv
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from agents.reader import run_reader_agent
from agents.writer import run_writer_agent
from agents.verifier import run_verifier_agent
from core.schemas import DocstringSchema

load_dotenv()


class GraphState(TypedDict):
    code: str
    context: str
    documentation: Optional[DocstringSchema]
    reviewer_feedback: str
    attempts: int


def node_reader(state: GraphState):
    result = run_reader_agent(state["code"])

    simulated_context = ""
    if not result.ready_to_write:
        print(f"   -> [Simulated Searcher]: Fetching answers for: {result.queries}")
        simulated_context = "The external function only validates if it is null."

    return {"context": simulated_context}


def node_writer(state: GraphState):
    current_context = state.get("context", "")

    if state.get("reviewer_feedback"):
        current_context += f"\nFIX THIS ERROR POINTED OUT BY THE REVIEWER: {state['reviewer_feedback']}"

    doc = run_writer_agent(state["code"], current_context)
    attempts = state.get("attempts", 0) + 1
    return {"documentation": doc, "attempts": attempts}


def node_verifier(state: GraphState):
    result = run_verifier_agent(state["code"], state["documentation"])
    if result.approved:
        print("Documentation Approved!")
        return {"reviewer_feedback": "APPROVED"}
    else:
        print(f"Documentation Rejected: {result.rejection_reason}")
        return {"reviewer_feedback": result.rejection_reason}


def decide_next_step(state: GraphState):
    if state["reviewer_feedback"] == "APPROVED":
        return END

    if state["attempts"] >= 3:
        print("Max attempts reached. Forcing termination.")
        return END

    return "writer"


workflow = StateGraph(GraphState)

workflow.add_node("reader", node_reader)
workflow.add_node("writer", node_writer)
workflow.add_node("verifier", node_verifier)

# Main Flow
workflow.set_entry_point("reader")
workflow.add_edge("reader", "writer")
workflow.add_edge("writer", "verifier")

# Conditional Flow (Loops back to writer or ends)
workflow.add_conditional_edges(
    "verifier",
    decide_next_step,
    {"writer": "writer", END: END}
)

app = workflow.compile()

if __name__ == "__main__":

    pathGit = "https://github.com/dosbox-staging/dosbox-staging.git"

    github_url = pathGit

    print("Starting the LangGraph agentic workflow...\n")

    repo_files = load_cpp_from_github(github_url, target_dir="./tmp_repo")

    if repo_files:
        first_file_path = list(repo_files.keys())[0]
        first_file_content = repo_files[first_file_path]

        print(f"\n Sending file to agents: {first_file_path}")

        initial_state = {
            "code": first_file_content,
            "context": f"File path: {first_file_path}",
            "documentation": None,
            "reviewer_feedback": "",
            "attempts": 0
        }

        final_result = app.invoke(initial_state)

        print("\n=============================================")
        print(f" FINAL RESULT FOR {first_file_path} ")
        print("=============================================")
        print(final_result["documentation"].model_dump_json(indent=2))

    else:
        print("No C/C++ files found in the specified repository.")


