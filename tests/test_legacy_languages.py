"""Cobertura real do extrator nas linguagens de codigo legado.

Este arquivo existe para nao repetir um erro que eu cometi: afirmar cobertura
sem medir. O `tree-sitter-language-pack` traz 371 gramaticas, mas carregar a
gramatica nao significa que o extrator generico ache simbolos nela.

Os testes abaixo separam explicitamente:

- FUNCIONA: o extrator encontra funcoes com nome; chunking por AST vale.
- DEGRADADO: a gramatica carrega mas nao rende simbolos; o arquivo cai no
  fallback de chunk por linha, com qualidade pior. Documentado, nao escondido.
"""

from __future__ import annotations

import pytest
from legacydoc_parsing import build_chunks, detect_language, parse_file

# --------------------------------------------------------------- amostras

AMOSTRAS: dict[str, tuple[str, str]] = {
    "pascal": (
        "calculo.pas",
        """
unit Calculo;
interface
function CalcularJuros(Capital: Double): Double;
implementation
function CalcularJuros(Capital: Double): Double;
begin
  if Capital <= 0 then
    raise Exception.Create('invalido');
  Result := Capital * 0.05;
end;
procedure GravarLog(Msg: string);
begin
  WriteLn(Msg);
end;
end.
""",
    ),
    "vb": (
        "Calculadora.vb",
        """
Public Class Calculadora
    Public Function CalcularJuros(ByVal capital As Double) As Double
        If capital <= 0 Then
            Throw New ArgumentException("invalido")
        End If
        Return capital * 0.05
    End Function
    Private Sub GravarLog(ByVal msg As String)
        Console.WriteLine(msg)
    End Sub
End Class
""",
    ),
    "ada": (
        "calculo.adb",
        """
package body Calculo is
   function Calcular_Juros (Capital : Float) return Float is
   begin
      if Capital <= 0.0 then
         raise Constraint_Error;
      end if;
      return Capital * 0.05;
   end Calcular_Juros;
end Calculo;
""",
    ),
    "fortran": (
        "calc.f90",
        """
      SUBROUTINE CALCJUROS(CAP, TAXA, RES)
      REAL CAP, TAXA, RES
      IF (CAP .LE. 0.0) THEN
         RES = 0.0
      ELSE
         RES = CAP * TAXA
      END IF
      END
""",
    ),
    "erlang": (
        "calculo.erl",
        """
-module(calculo).
calcular_juros(Capital, Taxa) when Capital > 0 ->
    Capital * Taxa;
calcular_juros(_, _) -> 0.
""",
    ),
    "powershell": (
        "Calculo.ps1",
        """
function Calcular-Juros {
    param([double]$Capital)
    if ($Capital -le 0) { throw "invalido" }
    return $Capital * 0.05
}
function Gravar-Log { param($Msg) Write-Host $Msg }
""",
    ),
    "perl": (
        "calculo.pl",
        """
sub calcular_juros {
    my ($capital, $taxa) = @_;
    if ($capital <= 0) { die "invalido"; }
    return $capital * $taxa;
}
sub gravar_log { my $m = shift; print $m; }
""",
    ),
    "objc": (
        "Calculadora.m",
        """
@implementation Calculadora
- (double)calcularJuros:(double)capital {
    if (capital <= 0) { return 0; }
    return capital * 0.05;
}
@end
""",
    ),
}

DEGRADADAS: dict[str, tuple[str, str]] = {
    "cobol": (
        "CALCJUROS.cbl",
        """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALCJUROS.
       PROCEDURE DIVISION.
       CALCULAR-JUROS.
           COMPUTE WS-JUROS = WS-CAPITAL * WS-TAXA.
       GRAVAR-REGISTRO.
           WRITE REG-SAIDA.
""",
    ),
    "groovy": (
        "Calculadora.groovy",
        """
class Calculadora {
    double calcularJuros(double capital) {
        if (capital <= 0) throw new IllegalArgumentException()
        return capital * 0.05
    }
}
""",
    ),
}


def _parse(path: str, source: str):
    language = detect_language(path)
    assert language is not None, f"extensao de {path} nao esta mapeada"
    return parse_file(path, source, language)


# ------------------------------------------------------------- cobertura


@pytest.mark.parametrize("language", sorted(AMOSTRAS))
def test_extracts_symbols_from_legacy_language(language: str):
    path, source = AMOSTRAS[language]
    parsed = _parse(path, source)

    assert not parsed.parse_failed, f"a gramatica de {language} nao carregou"
    assert parsed.symbols, f"o extrator nao achou nenhum simbolo em {language}"
    assert all(symbol.name for symbol in parsed.symbols), "todo simbolo precisa ter nome"


def test_pascal_encontra_funcao_e_procedimento():
    """Delphi/Object Pascal: `defProc` cobre function e procedure."""
    parsed = _parse(*AMOSTRAS["pascal"])
    nomes = {symbol.name for symbol in parsed.symbols}

    assert "CalcularJuros" in nomes
    assert "GravarLog" in nomes


def test_visual_basic_finds_function_and_sub_inside_class():
    parsed = _parse(*AMOSTRAS["vb"])
    nomes = {symbol.name for symbol in parsed.symbols}

    assert "CalcularJuros" in nomes
    assert "GravarLog" in nomes


def test_complexity_is_measured_for_legacy_language():
    """A ramificacao precisa ser contada tambem fora das linguagens modernas."""
    parsed = _parse(*AMOSTRAS["vb"])
    com_if = next(s for s in parsed.symbols if s.name == "CalcularJuros")

    assert com_if.complexity > 1


# ------------------------------------------------------------- degradadas


@pytest.mark.parametrize("language", sorted(DEGRADADAS))
def test_linguagem_degradada_ainda_e_processavel(language: str):
    """Sem simbolos, mas o arquivo nao pode ser perdido nem estourar.

    Se algum dia a gramatica melhorar e este teste comecar a achar simbolos,
    ele falha de proposito: e o sinal para promover a linguagem para AMOSTRAS.
    """
    path, source = DEGRADADAS[language]
    parsed = _parse(path, source)
    chunks = build_chunks(parsed, max_tokens_per_chunk=6000)

    assert not parsed.symbols, (
        f"{language} passou a render simbolos - mova para AMOSTRAS e remova daqui"
    )
    assert chunks, "o arquivo precisa gerar ao menos um chunk mesmo sem simbolos"
    assert all(chunk.truncated for chunk in chunks), (
        "chunk por linha precisa vir marcado, para o Writer saber que a fronteira e arbitraria"
    )


def test_legacy_extensions_are_mapped():
    for extensao, esperado in (
        (".pas", "pascal"),
        (".dpr", "pascal"),
        (".vb", "vb"),
        (".bas", "vb"),
        (".frm", "vb"),
        (".adb", "ada"),
        (".erl", "erlang"),
        (".ps1", "powershell"),
        (".cbl", "cobol"),
        (".cob", "cobol"),
    ):
        language = detect_language(f"arquivo{extensao}")
        assert language is not None, f"{extensao} nao mapeada"
        assert language.name == esperado
