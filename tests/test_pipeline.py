"""Orchestrator and context selection tests.

Covers v1's silent defect: the retry comparison was always false, so the
verifier ran on the most expensive model in the pipeline and its result was
discarded. No rewrite ever happened.
"""

from __future__ import annotations

from dataclasses import replace

from legacydoc_agents import DocumentationPipeline, PipelineOptions
from legacydoc_agents.context_selector import (
    ContextCandidate,
    render_context,
    select_context,
)
from legacydoc_core.domain import (
    FindingDraft,
    ImproverOutput,
    SymbolDoc,
    VerifierOutput,
    WriterOutput,
)
from legacydoc_core.plans import GenerationDepth, PlanTier, get_plan, resolve_depth
from legacydoc_parsing import detect_language
from legacydoc_providers.base import StructuredResult, Usage
from legacydoc_providers.router import AgentRole

SOURCE = (
    "def somar(a, b):\n"
    "    return a + b\n"
    "\n"
    "def dividir(a, b):\n"
    "    if b == 0:\n"
    "        raise ValueError('divisao por zero')\n"
    "    return a / b\n"
)


def _symbol(name: str, description: str = "Descricao original.") -> SymbolDoc:
    return SymbolDoc(
        name=name,
        kind="function",
        signature=f"def {name}(a, b)",
        language="python",
        summary=f"Resumo de {name}.",
        description=description,
    )


class ScriptedRouter:
    """Fake router returning scripted responses per role."""

    def __init__(self, responses: dict[AgentRole, list]) -> None:
        self._responses = {role: list(items) for role, items in responses.items()}
        self.calls: list[AgentRole] = []
        self.cacheable_prefixes: list[str] = []
        self.cache_keys: list[str] = []

    async def complete(self, role, *, system, user, schema, cacheable_prefix="", cache_key=""):
        self.calls.append(role)
        self.cacheable_prefixes.append(cacheable_prefix)
        self.cache_keys.append(cache_key)
        queue = self._responses.get(role)

        if not queue:
            raise AssertionError(f"papel {role} chamado sem resposta programada")

        value = queue.pop(0) if len(queue) > 1 else queue[0]

        return StructuredResult(
            value=value,
            provider="fake",
            model="fake-model",
            usage=Usage(10, 10),
            latency_ms=1,
        )

    def count(self, role: AgentRole) -> int:
        return sum(1 for item in self.calls if item == role)


def _reader_ok():
    from pydantic import BaseModel

    class ReaderOutput(BaseModel):
        ready_to_write: bool = True
        queries: str = ""
        user_facing_message: str = ""

    return ReaderOutput()


async def _run(
    router,
    plan_tier: PlanTier,
    *,
    options: PipelineOptions | None = None,
    depth: GenerationDepth | None = None,
):
    """Mirrors production: the depth is what was asked, capped by the plan.

    Passing no depth means the caller wants everything the plan pays for,
    which is what the API does when the request omits the field.
    """
    plan = get_plan(plan_tier)

    pipeline = DocumentationPipeline(
        router,
        plan,
        replace(
            options or PipelineOptions(generate_summary=False),
            depth=resolve_depth(depth, plan),
        ),
    )

    return await pipeline.run(
        path="calc.py",
        source=SOURCE,
        language=detect_language("calc.py"),
    )


async def test_free_plan_documents_without_findings_or_verifier():
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("somar"), _symbol("dividir")])],
        }
    )

    result = await _run(router, PlanTier.FREE)

    assert {s.name for s in result.documentation.symbols} == {"somar", "dividir"}
    assert result.documentation.findings == []
    assert router.count(AgentRole.IMPROVER) == 0
    assert router.count(AgentRole.VERIFIER) == 0, (
        "the Free plan does not pay for the expensive model"
    )


async def test_pro_plan_runs_improver_and_verifier():
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("somar")])],
            AgentRole.IMPROVER: [
                ImproverOutput(
                    findings=[
                        FindingDraft(
                            category="correctness",
                            severity="medium",
                            title="Sem validacao de tipo",
                            detail="Aceita qualquer coisa somavel.",
                        )
                    ]
                )
            ],
            AgentRole.VERIFIER: [
                VerifierOutput(approved=True, audit_notes="ok", feedback_message="Aprovado.")
            ],
        }
    )

    result = await _run(router, PlanTier.PRO)

    assert len(result.documentation.findings) == 1
    assert result.verifier_approved is True
    assert router.count(AgentRole.VERIFIER) == 1


async def test_rejected_symbols_are_actually_rewritten():
    """The v1 bug: the verifier rejected and nothing was rewritten."""
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [
                WriterOutput(symbols=[_symbol("somar", "Descricao errada.")]),
                WriterOutput(symbols=[_symbol("somar", "Descricao corrigida.")]),
            ],
            AgentRole.IMPROVER: [ImproverOutput()],
            AgentRole.VERIFIER: [
                VerifierOutput(
                    approved=False,
                    rejected_symbols=["somar"],
                    audit_notes="A descricao cita um parametro inexistente.",
                    feedback_message="Precisa ajustar.",
                ),
                VerifierOutput(approved=True, audit_notes="ok", feedback_message="Aprovado."),
            ],
        }
    )

    result = await _run(
        router, PlanTier.PRO, options=PipelineOptions(generate_summary=False, max_review_rounds=1)
    )

    assert result.review_rounds == 1
    assert result.documentation.symbols[0].description == "Descricao corrigida."
    assert router.count(AgentRole.WRITER) == 2


async def test_review_stops_after_max_rounds():
    stubborn = VerifierOutput(
        approved=False,
        rejected_symbols=["somar"],
        audit_notes="continua errado",
        feedback_message="Ainda nao.",
    )
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("somar")])],
            AgentRole.IMPROVER: [ImproverOutput()],
            AgentRole.VERIFIER: [stubborn],
        }
    )

    result = await _run(
        router, PlanTier.PRO, options=PipelineOptions(generate_summary=False, max_review_rounds=1)
    )

    assert result.verifier_approved is False
    assert any("sobreviveram" in warning for warning in result.warnings)
    assert router.count(AgentRole.VERIFIER) == 2, "must not loop forever"


async def test_parser_data_overrides_model_guesses():
    """Lines and complexity come from the AST: verifiable and free."""
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("dividir")])],
        }
    )

    result = await _run(router, PlanTier.FREE)
    dividir = result.documentation.symbols[0]

    assert dividir.line_start == 4
    assert dividir.complexity_estimate is not None and dividir.complexity_estimate > 1


async def test_findings_are_sorted_by_severity():
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("somar")])],
            AgentRole.IMPROVER: [
                ImproverOutput(
                    findings=[
                        FindingDraft(category="testing", severity="low", title="Baixo", detail="d"),
                        FindingDraft(
                            category="security", severity="critical", title="Critico", detail="d"
                        ),
                    ]
                )
            ],
            AgentRole.VERIFIER: [
                VerifierOutput(approved=True, audit_notes="ok", feedback_message="ok")
            ],
        }
    )

    result = await _run(router, PlanTier.PRO)

    assert [f.title for f in result.documentation.findings] == ["Critico", "Baixo"]


async def test_empty_file_returns_warning_not_crash():
    router = ScriptedRouter({AgentRole.READER: [_reader_ok()]})

    pipeline = DocumentationPipeline(router, get_plan(PlanTier.FREE))
    result = await pipeline.run(path="v.py", source="\n", language=detect_language("v.py"))

    assert result.documentation.symbols == []
    assert result.warnings


# ---------------------------------------------------------- contexto


def _candidate(**kwargs) -> ContextCandidate:
    defaults = {
        "id": "1",
        "kind": "glossary",
        "title": "Termo",
        "content": "conteudo",
        "path_globs": (),
        "tags": (),
        "weight": 100,
    }
    return ContextCandidate(**{**defaults, "id": kwargs.pop("id", "1"), **kwargs})


def test_glob_targets_the_right_files():
    auth = _candidate(id="a", title="Auth", content="tokens", path_globs=("src/auth/**",))
    billing = _candidate(id="b", title="Billing", content="faturas", path_globs=("src/billing/**",))

    chosen = select_context(
        [auth, billing], file_path="src/auth/login.py", code_sample="def x(): pass"
    )

    assert [item.id for item in chosen] == ["a"], "a non-matching glob is an explicit no"


def test_lexical_overlap_ranks_relevant_context_first():
    relevante = _candidate(id="r", title="Pagamento", content="fatura pagamento cobranca invoice")
    irrelevante = _candidate(id="i", title="Mapas", content="latitude longitude geocodificacao")

    chosen = select_context(
        [irrelevante, relevante],
        file_path="src/invoice.py",
        code_sample="def gerar_invoice(pagamento, cobranca): pass",
    )

    assert chosen[0].id == "r"


def test_selection_respects_the_character_budget():
    grandes = [_candidate(id=str(i), content="palavra " * 500) for i in range(10)]

    chosen = select_context(grandes, file_path="a.py", code_sample="palavra", max_chars=2000)

    assert sum(len(item.content) for item in chosen) <= 2000


def test_render_context_is_empty_without_items():
    assert render_context([]) == ""


def test_render_context_labels_each_item_by_kind():
    rendered = render_context([_candidate(kind="convention", title="Estilo", content="snake_case")])

    assert "[convention] Estilo" in rendered
    assert "snake_case" in rendered


async def test_invented_symbol_is_discarded():
    """The parser knows which symbols exist; hallucination must not persist.

    Without this filter an invented function became real documentation in the
    database with line_start=0.
    """
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [
                WriterOutput(
                    symbols=[
                        _symbol("somar"),
                        _symbol("processar_pagamento", "Funcao que nao existe no arquivo."),
                    ]
                )
            ],
        }
    )

    result = await _run(router, PlanTier.FREE)
    nomes = {s.name for s in result.documentation.symbols}

    assert "somar" in nomes
    assert "processar_pagamento" not in nomes, (
        "a symbol absent from the code must not be documented"
    )
    assert any(
        "processar_pagamento" in aviso and "descartado" in aviso.lower()
        for aviso in result.warnings
    ), f"o descarte precisa ficar visivel ao usuario; avisos: {result.warnings}"


async def test_class_qualified_method_is_accepted():
    """The model sometimes returns Class.method; the parser stores method."""
    fonte = "class Carrinho:\n    def adicionar(self, item):\n        return item\n"

    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("Carrinho.adicionar")])],
        }
    )

    pipeline = DocumentationPipeline(
        router, get_plan(PlanTier.FREE), PipelineOptions(generate_summary=False)
    )
    result = await pipeline.run(path="c.py", source=fonte, language=detect_language("c.py"))

    assert len(result.documentation.symbols) == 1, "must not be mistaken for hallucination"
    assert result.documentation.symbols[0].line_start == 2


async def test_nothing_is_discarded_without_parser_ground_truth():
    """A file whose grammar failed has no ground truth to compare against.

    Discarding everything would leave the user with no documentation at all;
    the right move is to accept and warn that nothing was verified.
    """
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("qualquer_coisa")])],
        }
    )

    pipeline = DocumentationPipeline(
        router, get_plan(PlanTier.FREE), PipelineOptions(generate_summary=False)
    )
    # Constants only: the parser recognises no symbols.
    fonte = "\n".join(f"CONST_{i} = {i}" for i in range(50))
    result = await pipeline.run(
        path="consts.py", source=fonte, language=detect_language("consts.py")
    )

    assert len(result.documentation.symbols) == 1


async def test_audit_sends_the_source_as_a_cacheable_prefix():
    """The file is identical on every review round; the documentation is not.

    Leading with the source lets the provider bill it at cache rates from the
    second round on, and the verifier runs on the most expensive model.
    """
    stubborn = VerifierOutput(
        approved=False,
        rejected_symbols=["somar"],
        audit_notes="still wrong",
        feedback_message="Not yet.",
    )
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("somar")])],
            AgentRole.IMPROVER: [ImproverOutput()],
            AgentRole.VERIFIER: [stubborn],
        }
    )

    await _run(
        router,
        PlanTier.PRO,
        options=PipelineOptions(generate_summary=False, max_review_rounds=1),
    )

    audit_prefixes = [
        prefix
        for role, prefix in zip(router.calls, router.cacheable_prefixes, strict=True)
        if role == AgentRole.VERIFIER
    ]

    assert len(audit_prefixes) == 2, "the loop must audit twice"
    assert audit_prefixes[0] == audit_prefixes[1], (
        "the cached prefix must be byte-identical or the cache never hits"
    )
    assert "def somar" in audit_prefixes[0], "the prefix must carry the source"


async def test_audit_uses_a_stable_cache_key_per_file():
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("somar")])],
            AgentRole.IMPROVER: [ImproverOutput()],
            AgentRole.VERIFIER: [
                VerifierOutput(approved=True, audit_notes="ok", feedback_message="ok")
            ],
        }
    )

    await _run(router, PlanTier.PRO)

    audit_keys = [
        key
        for role, key in zip(router.calls, router.cache_keys, strict=True)
        if role == AgentRole.VERIFIER
    ]

    assert audit_keys == ["verifier:calc.py"]


async def test_documentation_is_not_part_of_the_cached_prefix():
    """It changes after every rewrite; caching it would never hit."""
    router = ScriptedRouter(
        {
            AgentRole.READER: [_reader_ok()],
            AgentRole.WRITER: [WriterOutput(symbols=[_symbol("somar")])],
            AgentRole.IMPROVER: [ImproverOutput()],
            AgentRole.VERIFIER: [
                VerifierOutput(approved=True, audit_notes="ok", feedback_message="ok")
            ],
        }
    )

    await _run(router, PlanTier.PRO)

    audit_prefix = next(
        prefix
        for role, prefix in zip(router.calls, router.cacheable_prefixes, strict=True)
        if role == AgentRole.VERIFIER
    )

    assert "DOCUMENTACAO GERADA" not in audit_prefix
