"""Repository-wide symbol index used as cross-file context for the writer agent.

Documenting a file in isolation leaves the model guessing what a call into
another file does. The parser already runs over every file in the job, so the
signatures are available at no token cost.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from legacydoc_parsing.symbols import ParsedFile

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

MAX_SIGNATURE_CHARS = 160
MIN_SYMBOL_NAME_LENGTH = 4

DEFAULT_MAX_SYMBOLS = 12
DEFAULT_MAX_CHARS = 2500

COMMON_IDENTIFIERS = frozenset(
    {
        "add",
        "bool",
        "class",
        "const",
        "data",
        "def",
        "dict",
        "err",
        "error",
        "false",
        "for",
        "func",
        "get",
        "init",
        "int",
        "item",
        "len",
        "let",
        "list",
        "main",
        "new",
        "none",
        "null",
        "print",
        "private",
        "public",
        "result",
        "return",
        "run",
        "self",
        "set",
        "static",
        "str",
        "string",
        "this",
        "true",
        "value",
        "var",
        "void",
        "while",
    }
)
"""Names that would match nearly every file without informing the model."""


@dataclass(frozen=True)
class IndexedSymbol:
    name: str
    kind: str
    signature: str
    path: str
    parent: str | None = None
    summary: str | None = None

    def render(self) -> str:
        location = f"{self.path} ({self.parent})" if self.parent else self.path
        lines = [f"{self.kind} {self.name} - definido em {location}"]

        if self.signature:
            lines.append(f"    {self.signature[:MAX_SIGNATURE_CHARS]}")
        if self.summary:
            lines.append(f"    {self.summary}")

        return "\n".join(lines)


def _is_indexable(name: str) -> bool:
    return len(name) >= MIN_SYMBOL_NAME_LENGTH and name.lower() not in COMMON_IDENTIFIERS


@dataclass
class SymbolIndex:
    definitions_by_name: dict[str, list[IndexedSymbol]] = field(default_factory=dict)
    indexed_paths: set[str] = field(default_factory=set)

    def add_file(self, parsed: ParsedFile) -> None:
        self.indexed_paths.add(parsed.path)

        for span in parsed.symbols:
            if not _is_indexable(span.name):
                continue

            self.definitions_by_name.setdefault(span.name, []).append(
                IndexedSymbol(
                    name=span.name,
                    kind=span.kind,
                    signature=span.signature,
                    path=parsed.path,
                    parent=span.parent,
                )
            )

    def attach_summaries(self, path: str, summaries: dict[str, str]) -> None:
        """Enrich already-indexed symbols once their file has been documented.

        Results depend on processing order: the first file of a job sees no
        summaries. Order is stable across runs because the scan is sorted.
        """
        for name, summary in summaries.items():
            definitions = self.definitions_by_name.get(name)

            if not definitions:
                continue

            self.definitions_by_name[name] = [
                (
                    IndexedSymbol(
                        name=definition.name,
                        kind=definition.kind,
                        signature=definition.signature,
                        path=definition.path,
                        parent=definition.parent,
                        summary=summary,
                    )
                    if definition.path == path and definition.summary is None
                    else definition
                )
                for definition in definitions
            ]

    def references_in(
        self,
        source: str,
        *,
        exclude_path: str,
        max_symbols: int = DEFAULT_MAX_SYMBOLS,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> list[IndexedSymbol]:
        """Return symbols from other files that this snippet mentions, most used first."""
        if not self.definitions_by_name:
            return []

        mention_counts = Counter(
            token for token in IDENTIFIER_PATTERN.findall(source) if _is_indexable(token)
        )

        candidates = [
            (count, definition)
            for token, count in mention_counts.items()
            for definition in self.definitions_by_name.get(token, ())
            if definition.path != exclude_path
        ]
        candidates.sort(key=lambda pair: (-pair[0], pair[1].path, pair[1].name))

        return self._fit_within_budget(candidates, max_symbols, max_chars)

    @staticmethod
    def _fit_within_budget(
        candidates: list[tuple[int, IndexedSymbol]],
        max_symbols: int,
        max_chars: int,
    ) -> list[IndexedSymbol]:
        selected: list[IndexedSymbol] = []
        seen: set[tuple[str, str]] = set()
        used_chars = 0

        for _, definition in candidates:
            key = (definition.path, definition.name)

            if key in seen:
                continue

            rendered = definition.render()

            if used_chars + len(rendered) > max_chars:
                continue

            seen.add(key)
            selected.append(definition)
            used_chars += len(rendered)

            if len(selected) >= max_symbols:
                break

        return selected

    @property
    def symbol_count(self) -> int:
        return sum(len(definitions) for definitions in self.definitions_by_name.values())

    @property
    def file_count(self) -> int:
        return len(self.indexed_paths)


def render_external_symbols(symbols: list[IndexedSymbol]) -> str:
    return "\n\n".join(symbol.render() for symbol in symbols)
