"""Parsing multi-linguagem baseado em tree-sitter."""

from legacydoc_parsing.chunking import CodeChunk, build_chunks, estimate_tokens
from legacydoc_parsing.languages import (
    LANGUAGES,
    SUPPORTED_EXTENSIONS,
    LanguageInfo,
    detect_language,
    extensions_by_language,
    is_supported,
)
from legacydoc_parsing.symbol_index import (
    IndexedSymbol,
    SymbolIndex,
    render_external_symbols,
)
from legacydoc_parsing.symbols import ParsedFile, SymbolSpan, parse_file

__all__ = [
    "LANGUAGES",
    "SUPPORTED_EXTENSIONS",
    "CodeChunk",
    "IndexedSymbol",
    "SymbolIndex",
    "LanguageInfo",
    "ParsedFile",
    "SymbolSpan",
    "build_chunks",
    "detect_language",
    "estimate_tokens",
    "extensions_by_language",
    "is_supported",
    "parse_file",
    "render_external_symbols",
]
