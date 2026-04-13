# agents/writer.py
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from core.schemas import DocstringSchema


def run_writer_agent(codigo_cpp: str, contexto_extra: str = "") -> DocstringSchema:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)


    llm_estruturada = llm.with_structured_output(DocstringSchema)


    prompt = ChatPromptTemplate.from_messages([
        ("system", """Você é o Agente Writer, um redator técnico sênior de C++.
        Sua tarefa é redigir a documentação técnica seguindo ESTRITAMENTE o formato solicitado.
        Não invente parâmetros ou exceções. Baseie-se apenas no código e contexto fornecidos."""),
        ("user", "Código C++:\n{codigo}\n\nContexto Extra (Searcher):\n{contexto}")
    ])

    chain = prompt | llm_estruturada

    print("✍️  [Writer]: Analisando código e escrevendo documentação estruturada...")
    resultado = chain.invoke({"code": codigo_cpp, "contexto": contexto_extra})

    return resultado