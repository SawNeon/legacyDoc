# agents/reader.py
import os
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


class ReaderOutput(BaseModel):
    ready_to_write: bool = Field(
        description="True if the code is self-sufficient (READY_FOR_WRITING), False if context is missing."
    )
    queries: str = Field(
        description="Internal logic in English: Technical queries for the Searcher/Developer if context is missing. Leave empty if ready."
    )
    user_facing_message: str = Field(
        description="A welcoming message in Brazilian Portuguese following the WaveCast brand voice, explaining the situation and asking ONE clarifying question if needed. If ready, just confirm readiness."
    )


def run_reader_agent(cpp_code: str) -> ReaderOutput:

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("ERRO CRÍTICO: OPENAI_API_KEY não foi encontrada nas variáveis de ambiente.")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

    structured_llm = llm.with_structured_output(ReaderOutput)

    system_prompt = """You are the Reader Agent of the Legacy Doc Team. 
    Your mission is to perform a "technical X-ray" of the legacy C++ code to identify what is missing for a perfect documentation.

    DIAGNOSTIC CRITERIA:
    1. Context Gap Identification: Analyze if there are external function calls, inherited classes, or global variables not defined in the provided snippet.
    2. Exception Detection: Check for throw statements or calls to external methods that might raise hidden exceptions (e.g., database or network calls).
    3. Critical Analysis: 
       - If the code is self-sufficient: mark ready_to_write as True and output "READY_FOR_WRITING".
       - If context is missing: mark ready_to_write as False and generate specific technical queries.

    RULES (Based on HRBP Framework):
    - Action & Situation: Clearly identify what the code is doing and in which context it operates before requesting more data.
    - One Question at a Time: If you need to clarify something with the user/leadership, ask ONLY ONE question to promote focus and reflection.

    BRAND VOICE (WaveCast):
    - Be the "Reliable Guide". Your language should be clear, avoiding unnecessary jargon, and always welcoming.
    - Start your user-facing message with something like: "Olá, Time WaveCast! Identifiquei uma lacuna no contexto deste módulo..." (if missing context) or a positive confirmation (if ready).

    LANGUAGE: 
    - Internal logic (queries field) MUST be in English.
    - User-facing questions (user_facing_message field) MUST be in Brazilian Portuguese.
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "C++ Code:\n{code}")
    ])

    chain = prompt | structured_llm

    print("🔍 [Reader Agent]: Fazendo o raio-X técnico do código via API OpenAI...")

    return chain.invoke({"code": cpp_code})