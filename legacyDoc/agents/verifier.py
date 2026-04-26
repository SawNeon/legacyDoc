# agents/verifier.py
import os
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from core.schemas import FileDocumentation


class VerifierOutput(BaseModel):
    approved: bool = Field(
        description="True if the documentation is 100% faithful to the code, False if there are hallucinations or missing elements."
    )
    technical_audit: str = Field(
        description="Internal logic in English: The strict technical comparison checking for hallucinations, signature match, and the Situation/Action/Impact model."
    )
    feedback_message: str = Field(
        description="Message in Brazilian Portuguese for the Writer/User. Must include specific praise, follow the WaveCast 'Precise and Encouraging' brand voice, and if rejected, include ONE reflective question."
    )


def run_verifier_agent(cpp_code: str, documentation: FileDocumentation) -> VerifierOutput:
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("ERRO CRÍTICO: OPENAI_API_KEY não foi encontrada nas variáveis de ambiente.")

    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    structured_llm = llm.with_structured_output(VerifierOutput)

    system_prompt = """You are the Verifier Agent, the final auditor of the Legacy Doc Team. 
    Your job is to ensure the documentation is 100% faithful to the original C++ code.

    AUDIT CRITERIA:
    1. Hallucination Check: Did the Writer invent any arguments, types, or exceptions?
    2. Technical Consistency: Do the args, returns, and raises match the C++ signature perfectly?
    3. Situational Model Audit: Does the description clearly explain the Situation, Action, and Impact as per WaveCast standards?

    RULES (Based on HRBP Framework):
    - Approval/Rejection:
      - If adequate: Approve (approved=True) and justify based on technical rules.
      - If inadequate: Reject (approved=False). Do not just reject; ask a reflective question to help the Writer improve (e.g., "Você mencionou um parâmetro 'timeout', mas ele não consta no código original. Poderia revisar?").
    - Specific Praise: Highlight where the documentation was particularly clear or humanized.

    BRAND VOICE (WaveCast):
    - Be "Precise and Encouraging". Even when rejecting, maintain a professional and welcoming tone (e.g., "Excelente esforço, Time! Mas precisamos ajustar um detalhe para garantir a precisão total.").

    LANGUAGE: 
    - Technical audit (technical_audit field) MUST be in English.
    - Feedback, praise, and Approval/Rejection communication (feedback_message field) MUST be in Brazilian Portuguese.
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "Original C++ Code:\n{code}\n\nGenerated Documentation:\n{doc}")
    ])

    chain = prompt | structured_llm
    print("⚖️  [Verifier Agent]: Realizando auditoria técnica e comportamental (Legacy Doc Standards)...")

    doc_json_str = documentation.model_dump_json()

    return chain.invoke({"code": cpp_code, "doc": doc_json_str})