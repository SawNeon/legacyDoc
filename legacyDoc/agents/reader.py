# agents/reader.py
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


class ReaderOutput(BaseModel):
    ready_to_write: bool = Field(description="True if the code has everything needed, False if context is missing.")
    queries: str = Field(
        description="If False, list what is missing (e.g., 'What does external function XYZ do?'). If True, leave empty.")


def run_reader_agent(cpp_code: str) -> ReaderOutput:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
    structured_llm = llm.with_structured_output(ReaderOutput)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are the Reader Agent. Analyze the legacy C++ code.
        Your mission is to check if we have the necessary context to fill out Args, Returns, and Raises.
        Are there calls to external functions not present in this code that might throw hidden errors? 
        If so, answer with ready_to_write=False and list the queries."""),
        ("user", "C++ Code:\n{code}")
    ])

    chain = prompt | structured_llm
    print("🔍  [Reader]: Analyzing dependencies and code gaps...")
    return chain.invoke({"code": cpp_code})