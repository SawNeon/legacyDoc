"""Testes de parsing e chunking.

O foco esta na regressao que motivou a reescrita: a v1 cortava o codigo a cada
150 linhas fixas, partia funcoes ao meio e o Writer, instruido a ignorar
definicoes incompletas, descartava a metade em silencio.
"""

from __future__ import annotations

import pytest
from legacydoc_parsing import build_chunks, detect_language, is_supported, parse_file
from legacydoc_parsing.chunking import estimate_tokens


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a.py", "python"),
        ("src/main.cpp", "cpp"),
        ("lib/util.h", "c"),
        ("app/Service.java", "java"),
        ("cmd/main.go", "go"),
        ("web/App.tsx", "tsx"),
        ("core/lib.rs", "rust"),
        ("scripts/deploy.sh", "bash"),
        ("legacy/CALC.f90", "fortran"),
    ],
)
def test_language_detection(path: str, expected: str):
    language = detect_language(path)

    assert language is not None
    assert language.name == expected


def test_unsupported_extension_returns_none():
    assert detect_language("README.md") is None
    assert detect_language("sem_extensao") is None
    assert not is_supported("dados.csv")


def _parse(path: str, source: str):
    language = detect_language(path)
    assert language is not None
    return parse_file(path, source, language)


def test_symbols_are_never_split_across_chunks():
    """A regressao central da v1."""
    functions = "\n\n".join(
        f"def funcao_{index}(a, b):\n"
        + "\n".join(f"    x_{line} = a + b + {line}" for line in range(40))
        + "\n    return a"
        for index in range(12)
    )

    parsed = _parse("grande.py", functions)
    chunks = build_chunks(parsed, max_tokens_per_chunk=800)

    assert len(chunks) > 1, "o arquivo precisa ser grande o bastante para dividir"

    for chunk in chunks:
        for symbol in chunk.symbols:
            # Each symbol's full body must be present in the chunk.
            assert symbol.source in chunk.source

    documented = {name for chunk in chunks for name in chunk.symbol_names}
    assert documented == {f"funcao_{index}" for index in range(12)}, (
        "nenhuma funcao pode sumir na divisao"
    )


def test_oversized_symbol_becomes_its_own_chunk():
    huge = "def gigante():\n" + "\n".join(f"    v{i} = {i}" for i in range(4000))

    parsed = _parse("gigante.py", huge)
    chunks = build_chunks(parsed, max_tokens_per_chunk=500)

    assert len(chunks) == 1
    assert chunks[0].truncated is True
    assert "TRUNCADO" in chunks[0].source, "o modelo precisa saber que viu um trecho"


def test_container_body_is_not_duplicated_in_the_chunk():
    """Classe e metodos no mesmo chunk nao podem repetir o mesmo codigo.

    Enviar o corpo duas vezes dobraria o custo de token em arquivos orientados
    a objeto.
    """
    source = (
        "class Servico:\n"
        "    def alpha(self):\n"
        "        return 1\n\n"
        "    def beta(self):\n"
        "        return 2\n"
    )

    parsed = _parse("servico.py", source)
    chunks = build_chunks(parsed, max_tokens_per_chunk=6000)

    assert chunks[0].source.count("return 1") == 1
    assert chunks[0].source.count("return 2") == 1


def test_methods_carry_their_parent():
    source = "class Repo:\n    def salvar(self, item):\n        return item\n"

    parsed = _parse("repo.py", source)
    metodo = next(s for s in parsed.symbols if s.name == "salvar")

    assert metodo.parent == "Repo"


def test_complexity_is_measured_not_guessed():
    simples = _parse("s.py", "def f():\n    return 1\n").symbols[0]

    ramificado = _parse(
        "r.py",
        "def g(a):\n"
        "    if a:\n"
        "        for i in range(3):\n"
        "            if i:\n"
        "                return i\n"
        "    return 0\n",
    ).symbols[0]

    assert simples.complexity == 1
    assert ramificado.complexity > simples.complexity


def test_container_has_no_complexity_score():
    """Somar a complexidade de todos os metodos nao significa nada."""
    parsed = _parse("c.py", "class A:\n    def m(self):\n        if 1:\n            return 2\n")
    classe = next(s for s in parsed.symbols if s.kind == "class")

    assert classe.complexity == 0


def test_chunk_header_lists_sibling_symbols():
    source = "def um():\n    return 1\n\ndef dois():\n    return 2\n"

    chunks = build_chunks(_parse("m.py", source), max_tokens_per_chunk=6000)

    assert "m.py" in chunks[0].source
    assert "um, dois" in chunks[0].source


def test_file_without_recognizable_symbols_falls_back_to_line_chunks():
    source = "\n".join(f"CONSTANTE_{i} = {i}" for i in range(500))

    chunks = build_chunks(_parse("consts.py", source), max_tokens_per_chunk=300)

    assert chunks, "arquivo so de constantes ainda precisa ser processavel"
    assert all(chunk.truncated for chunk in chunks)


def test_empty_file_produces_no_chunks():
    assert build_chunks(_parse("vazio.py", "\n\n")) == []


def test_token_estimate_grows_with_size():
    assert estimate_tokens("x" * 360) > estimate_tokens("x" * 36)
