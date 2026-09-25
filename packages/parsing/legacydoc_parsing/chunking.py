"""Group symbols into chunks that fit the prompt budget."""

from __future__ import annotations

from dataclasses import dataclass, field

from legacydoc_parsing.symbols import ParsedFile, SymbolSpan

CHARS_PER_TOKEN = 3.6


def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


@dataclass
class CodeChunk:
    """A coherent slice of code sent to one LLM call."""

    index: int
    source: str
    symbols: list[SymbolSpan] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0
    truncated: bool = False

    @property
    def symbol_names(self) -> list[str]:
        return [symbol.name for symbol in self.symbols]

    @property
    def estimated_tokens(self) -> int:
        return estimate_tokens(self.source)


def build_chunks(
    parsed: ParsedFile,
    *,
    max_tokens_per_chunk: int = 6000,
    include_file_header: bool = True,
) -> list[CodeChunk]:
    """Split a file into chunks that respect symbol boundaries."""
    if not parsed.symbols:
        return _fallback_line_chunks(parsed, max_tokens_per_chunk)

    header = _file_header(parsed) if include_file_header else ""
    header_tokens = estimate_tokens(header)
    budget = max(max_tokens_per_chunk - header_tokens, 512)

    chunks: list[CodeChunk] = []
    current: list[SymbolSpan] = []
    current_tokens = 0

    for symbol in parsed.symbols:
        symbol_tokens = estimate_tokens(symbol.source)

        if symbol_tokens > budget:
            if current:
                chunks.append(_make_chunk(len(chunks), current, header))
                current, current_tokens = [], 0

            chunks.append(_make_oversized_chunk(len(chunks), symbol, header, budget))
            continue

        if current and current_tokens + symbol_tokens > budget:
            chunks.append(_make_chunk(len(chunks), current, header))
            current, current_tokens = [], 0

        current.append(symbol)
        current_tokens += symbol_tokens

    if current:
        chunks.append(_make_chunk(len(chunks), current, header))

    return chunks


def _file_header(parsed: ParsedFile) -> str:
    """Header naming the file and its sibling symbols."""
    names = ", ".join(symbol.name for symbol in parsed.symbols[:40]) or "nenhum"

    return (
        f"// Arquivo: {parsed.path}\n"
        f"// Linguagem: {parsed.language}\n"
        f"// Simbolos no arquivo: {names}\n\n"
    )


def _make_chunk(index: int, symbols: list[SymbolSpan], header: str) -> CodeChunk:
    body = "\n\n".join(symbol.source for symbol in symbols)

    return CodeChunk(
        index=index,
        source=f"{header}{body}",
        symbols=list(symbols),
        line_start=min(symbol.line_start for symbol in symbols),
        line_end=max(symbol.line_end for symbol in symbols),
    )


def _make_oversized_chunk(index: int, symbol: SymbolSpan, header: str, budget: int) -> CodeChunk:
    """A single symbol above budget: sent alone, truncated when necessary."""
    max_chars = int(budget * CHARS_PER_TOKEN)
    source = symbol.source
    truncated = len(source) > max_chars

    if truncated:
        source = (
            source[:max_chars] + "\n\n// [TRUNCADO] O corpo desta funcao excede o limite do modelo."
        )

    return CodeChunk(
        index=index,
        source=f"{header}{source}",
        symbols=[symbol],
        line_start=symbol.line_start,
        line_end=symbol.line_end,
        truncated=truncated,
    )


def _fallback_line_chunks(parsed: ParsedFile, max_tokens_per_chunk: int) -> list[CodeChunk]:
    """No recognised symbols: fall back to line-based cuts."""
    lines = parsed.source.split("\n")
    max_chars = int(max_tokens_per_chunk * CHARS_PER_TOKEN)

    chunks: list[CodeChunk] = []
    current: list[str] = []
    current_chars = 0
    start_line = 1

    for offset, line in enumerate(lines, start=1):
        current.append(line)
        current_chars += len(line) + 1

        if current_chars >= max_chars:
            chunks.append(
                CodeChunk(
                    index=len(chunks),
                    source="\n".join(current),
                    line_start=start_line,
                    line_end=offset,
                    truncated=True,
                )
            )
            current, current_chars = [], 0
            start_line = offset + 1

    if current and any(line.strip() for line in current):
        chunks.append(
            CodeChunk(
                index=len(chunks),
                source="\n".join(current),
                line_start=start_line,
                line_end=len(lines),
                truncated=True,
            )
        )

    return chunks
