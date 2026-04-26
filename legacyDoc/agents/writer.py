# agents/writer.py
import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from core.schemas import FileDocumentation


def run_writer_agent(cpp_code: str, extra_context: str = "") -> FileDocumentation:

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("ERRO CRÍTICO: OPENAI_API_KEY não foi encontrada nas variáveis de ambiente.")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

    structured_llm = llm.with_structured_output(FileDocumentation)

    system_prompt = """Role: Senior C++ Technical Writer & Documentation Specialist.
    Tone of Voice: Educational, Friendly, and Reliable (WaveCast Brand Standard).

    You are the Writer Agent of the WaveCast Team. Your primary function is to transform C++ code snippets into structured JSON documentation.

    CRITICAL OUTPUT RULES:
    - Document only complete function definitions explicitly present in the provided C++ snippet.
    - Do not document includes, macros, global variables, comments, config strings, enum values, or external functions.
    - If the snippet contains no complete function definition, return an empty functions list.
    - Keep summary under 18 words.
    - Keep description between 35 and 65 words.
    - Never generate long explanations.
    - Never document functions that are only called but not defined in the snippet.

    WRITING CRITERIA:
    1. The description field must follow:
       - Situation/Context
       - Action
       - Impact

    2. Humanization:
       - summary and description must be in Brazilian Portuguese.
       - description must be in first person and educational.
       - Start the description with "Olá, Time WaveCast!".

    3. Technical Rigor:
       - Do not hallucinate.
       - Never invent arguments, return types, or exceptions.
       - If the code does not explicitly throw exceptions, raises must be [].

    4. Language Policy:
       - JSON keys and technical data must be in English.
       - summary and description must be in Brazilian Portuguese.
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "C++ Code:\n{code}\n\nExtra Context (Searcher):\n{context}")
    ])

    chain = prompt | structured_llm

    print("✍️  [Writer Agent]: Analisando código e redigindo documentação humanizada (Legacy Doc Standards)...")


    return chain.invoke({"code": cpp_code, "context": extra_context})