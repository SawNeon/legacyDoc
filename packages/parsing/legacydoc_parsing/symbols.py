"""Language-agnostic symbol extraction with tree-sitter."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from legacydoc_parsing.languages import LanguageInfo

logger = logging.getLogger(__name__)

FUNCTION_NODE_TYPES: frozenset[str] = frozenset(
    {
        "function_definition",
        "function_declaration",
        "function_item",
        "method_definition",
        "method_declaration",
        "constructor_declaration",
        "destructor_declaration",
        "subroutine",
        "function",
        "method",
        "arrow_function",
        "lambda",
        "def",
        "singleton_method",
        "local_function_statement",
        "function_signature",
        "external_declaration",
        "defProc",
        "function_clause",
        "subprogram_body",
        "subroutine_declaration_statement",
        "function_statement",
    }
)

_IDENTIFIER_NODE_TYPES: frozenset[str] = frozenset(
    {
        "identifier",
        "type_identifier",
        "field_identifier",
        "word",
        "atom",
        "name",
        "function_name",
        "bareword",
    }
)

CONTAINER_NODE_TYPES: frozenset[str] = frozenset(
    {
        "class_definition",
        "class_declaration",
        "class_specifier",
        "struct_specifier",
        "struct_item",
        "struct_declaration",
        "interface_declaration",
        "trait_item",
        "impl_item",
        "enum_declaration",
        "enum_specifier",
        "module",
        "namespace_definition",
        "object_declaration",
        "record_declaration",
        "protocol_declaration",
        "extension_declaration",
        "type_declaration",
        "package_body",
    }
)

_BRANCH_NODE_TYPES: frozenset[str] = frozenset(
    {
        "if_statement",
        "elif_clause",
        "else_clause",
        "for_statement",
        "for_range_loop",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "switch_statement",
        "case_statement",
        "switch_section",
        "catch_clause",
        "except_clause",
        "rescue",
        "conditional_expression",
        "ternary_expression",
        "match_arm",
        "when_entry",
        "guard_statement",
    }
)

_BRANCH_OPERATORS: frozenset[str] = frozenset({"&&", "||", "and", "or", "??"})


@dataclass
class SymbolSpan:
    """A symbol located in the file, not yet documented."""

    name: str
    kind: str
    source: str
    line_start: int
    line_end: int
    byte_start: int
    byte_end: int
    parent: str | None = None
    signature: str = ""
    complexity: int = 1

    @property
    def line_count(self) -> int:
        return self.line_end - self.line_start + 1


@dataclass
class ParsedFile:
    path: str
    language: str
    source: str
    symbols: list[SymbolSpan] = field(default_factory=list)
    parse_failed: bool = False

    @property
    def line_count(self) -> int:
        return self.source.count("\n") + 1


def _get_parser(language: LanguageInfo):
    """Load the grammar parser. Imported late because the package is heavy."""
    from tree_sitter_language_pack import get_parser

    return get_parser(language.name)  # type: ignore[arg-type]


def parse_file(path: str, source: str, language: LanguageInfo) -> ParsedFile:
    """Extract the meaningful symbols from a file."""
    parsed = ParsedFile(path=path, language=language.name, source=source)

    try:
        parser = _get_parser(language)
        tree = parser.parse(source.encode("utf-8"))
    except Exception as exc:
        logger.warning("Tree-sitter could not load grammar %s: %s", language.name, exc)
        parsed.parse_failed = True
        return parsed

    source_bytes = source.encode("utf-8")
    parsed.symbols = _collect(tree.root_node, source_bytes, parent=None)
    parsed.symbols.sort(key=lambda symbol: symbol.byte_start)

    return parsed


def _collect(node, source_bytes: bytes, *, parent: str | None) -> list[SymbolSpan]:
    """Walk the tree collecting functions, descending into containers for methods."""
    found: list[SymbolSpan] = []

    for child in node.children:
        node_type = child.type

        if node_type in FUNCTION_NODE_TYPES:
            symbol = _build_symbol(child, source_bytes, parent=parent, kind="function")
            if symbol is not None:
                found.append(symbol)
            continue

        if node_type in CONTAINER_NODE_TYPES:
            container_name = _node_name(child, source_bytes)
            container = _build_symbol(
                child,
                source_bytes,
                parent=parent,
                kind=_container_kind(node_type),
                include_body=False,
            )

            if container is not None:
                found.append(container)

            qualified = (
                f"{parent}.{container_name}" if parent and container_name else container_name
            )
            found.extend(_collect(child, source_bytes, parent=qualified or parent))
            continue

        found.extend(_collect(child, source_bytes, parent=parent))

    return found


def _container_kind(node_type: str) -> str:
    if "interface" in node_type or "protocol" in node_type or "trait" in node_type:
        return "interface"
    if "namespace" in node_type or node_type == "module":
        return "namespace"
    if node_type == "impl_item" or "extension" in node_type:
        return "impl"
    if "struct" in node_type or "record" in node_type:
        return "struct"
    if "enum" in node_type:
        return "enum"
    return "class"


def _build_symbol(
    node,
    source_bytes: bytes,
    *,
    parent: str | None,
    kind: str,
    include_body: bool = True,
) -> SymbolSpan | None:
    name = _node_name(node, source_bytes)

    if not name:
        return None

    full_source = source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    source = full_source if include_body else _declaration_header(full_source)

    return SymbolSpan(
        name=name,
        kind=kind,
        source=source,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        byte_start=node.start_byte,
        byte_end=node.end_byte,
        parent=parent,
        signature=_extract_signature(full_source),
        complexity=_cyclomatic_complexity(node) if include_body else 0,
    )


def _declaration_header(source: str) -> str:
    """Take a container declaration without its method bodies."""
    candidates = [index for index in (source.find("{"), source.find("\n")) if index > 0]

    if not candidates:
        return source[:400].strip()

    return source[: min(candidates) + 1].strip()


def _node_name(node, source_bytes: bytes) -> str:
    """Resolve the symbol name."""
    named = node.child_by_field_name("name")

    if named is not None:
        return source_bytes[named.start_byte : named.end_byte].decode("utf-8", errors="replace")

    declarator = node.child_by_field_name("declarator")

    while declarator is not None:
        inner = declarator.child_by_field_name("declarator")
        if inner is None:
            break
        declarator = inner

    if declarator is not None:
        text = source_bytes[declarator.start_byte : declarator.end_byte].decode(
            "utf-8", errors="replace"
        )
        return text.split("(")[0].strip().lstrip("*&")

    for child in node.children:
        if child.type in _IDENTIFIER_NODE_TYPES:
            return source_bytes[child.start_byte : child.end_byte].decode("utf-8", errors="replace")

    return _shallow_identifier(node, source_bytes, depth=2)


def _shallow_identifier(node, source_bytes: bytes, *, depth: int) -> str:
    if depth <= 0:
        return ""

    for child in node.children:
        if child.type in _IDENTIFIER_NODE_TYPES:
            return source_bytes[child.start_byte : child.end_byte].decode("utf-8", errors="replace")

    for child in node.children:
        found = _shallow_identifier(child, source_bytes, depth=depth - 1)
        if found:
            return found

    return ""


def _extract_signature(source: str) -> str:
    """The leading line up to the body opener."""
    for terminator in ("{", ":", "=>", "\n"):
        index = source.find(terminator)
        if index > 0:
            candidate = source[:index].strip()
            if candidate:
                return " ".join(candidate.split())[:400]

    return " ".join(source.split())[:400]


def _cyclomatic_complexity(node) -> int:
    """Approximate cyclomatic complexity: one plus the branch points."""
    count = 1
    stack = [node]

    while stack:
        current = stack.pop()

        if (
            current.type in _BRANCH_NODE_TYPES
            or not current.child_count
            and current.type in _BRANCH_OPERATORS
        ):
            count += 1

        stack.extend(current.children)

    return count
