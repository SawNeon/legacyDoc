from typing import TypedDict, List, Optional
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END

class ArgDetail(BaseModel):
    name: str = Field(description="Nome do parâmetro")
    type: str = Field(description="Tipo de dado")
    description: str = Field(description="Descrição do parâmetro")


class RaiseDetail(BaseModel):
    exception: str = Field(description="Nome da Exceção")
    condition: str = Field(description="Condição do erro")


class DocstringSchema(BaseModel):
    summary: str = Field(description="Resumo curto")
    description: str = Field(description="Explicação detalhada")
    args: List[ArgDetail] = Field(default=[])
    returns: str = Field(description="O que a função retorna")
    raises: List[RaiseDetail] = Field(default=[])


class AgentState(TypedDict):
    codigo_legado: str
    documentacao: Optional[DocstringSchema]
    status: str



def reader_agent(state: AgentState):
    print("🔍 [Reader]: Lendo o código legado e buscando dependências...")
    return {"status": "analisado"}


def writer_agent(state: AgentState):
    print("✍️ [Writer]: Preenchendo os campos rigorosamente...")

    doc_mock = DocstringSchema(
        summary="Calcula o valor do imposto.",
        description="Esta função recebe um valor bruto e aplica a taxa de 10%.",
        args=[ArgDetail(name="valor", type="float", description="Valor original da compra")],
        returns="float (Valor final com imposto)",
        raises=[RaiseDetail(exception="ValueError", condition="Se o valor for negativo")]
    )
    return {"documentacao": doc_mock, "status": "escrito"}


def verifier_agent(state: AgentState):
    print("⚖️ [Verifier]: Checando se existem alucinações...")
    return {"status": "aprovado"}


workflow = StateGraph(AgentState)

workflow.add_node("reader", reader_agent)
workflow.add_node("writer", writer_agent)
workflow.add_node("verifier", verifier_agent)

workflow.set_entry_point("reader")
workflow.add_edge("reader", "writer")
workflow.add_edge("writer", "verifier")
workflow.add_edge("verifier", END)


app = workflow.compile()

if __name__ == "__main__":
    print("🚀 Iniciando o pipeline do DocAgent...\n")

    codigo_exemplo = """
    def calcular_imposto(valor):
        if valor < 0:
            raise ValueError("Valor inválido")
        return valor * 1.10
    """

    estado_inicial = {"codigo_legado": codigo_exemplo, "status": "inicio"}
    resultado_final = app.invoke(estado_inicial)

    print("\n✅ Documentação Final Gerada (Formato JSON Limpo):")
    print(resultado_final["documentacao"].model_dump_json(indent=2))