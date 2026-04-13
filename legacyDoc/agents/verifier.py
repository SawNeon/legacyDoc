# agents/verifier.py
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from core.schemas import DocstringSchema


class VerifierOutput(BaseModel):
    approved: bool = Field(
        description="True if the documentation is faithful to the code, False if there are hallucinations.")
    rejection_reason: str = Field(description="If rejected, explain exactly which Pydantic field is wrong and why.")


def run_verifier_agent(cpp_code: str, documentation: DocstringSchema) -> VerifierOutput:

    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    structured_llm = llm.with_structured_output(VerifierOutput)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are the Verifier Agent, a strict C++ code auditor.
        Compare the original code with the generated JSON documentation.
        Rejection Rules:
        1. If the documentation lists an argument in 'Args' that doesn't exist in the original code.
        2. If it lists an exception in 'Raises' that is impossible to be thrown by this snippet.
        Be strict."""),
        ("user", "Original C++ Code:\n{code}\n\nGenerated Documentation:\n{doc}")
    ])

    chain = prompt | structured_llm
    print("⚖️   [Verifier]: Checking for hallucinations in the documentation...")

    doc_json_str = documentation.model_dump_json()
    return chain.invoke({"code": cpp_code, "doc": doc_json_str})