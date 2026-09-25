"""Language detection from file extension."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class LanguageInfo:
    name: str
    display_name: str
    line_comment: str
    block_comment: tuple[str, str] | None = None


LANGUAGES: dict[str, LanguageInfo] = {
    "c": LanguageInfo("c", "C", "//", ("/*", "*/")),
    "cpp": LanguageInfo("cpp", "C++", "//", ("/*", "*/")),
    "csharp": LanguageInfo("csharp", "C#", "//", ("/*", "*/")),
    "go": LanguageInfo("go", "Go", "//", ("/*", "*/")),
    "java": LanguageInfo("java", "Java", "//", ("/*", "*/")),
    "javascript": LanguageInfo("javascript", "JavaScript", "//", ("/*", "*/")),
    "typescript": LanguageInfo("typescript", "TypeScript", "//", ("/*", "*/")),
    "tsx": LanguageInfo("tsx", "TypeScript (TSX)", "//", ("/*", "*/")),
    "python": LanguageInfo("python", "Python", "#", None),
    "ruby": LanguageInfo("ruby", "Ruby", "#", None),
    "rust": LanguageInfo("rust", "Rust", "//", ("/*", "*/")),
    "php": LanguageInfo("php", "PHP", "//", ("/*", "*/")),
    "kotlin": LanguageInfo("kotlin", "Kotlin", "//", ("/*", "*/")),
    "swift": LanguageInfo("swift", "Swift", "//", ("/*", "*/")),
    "scala": LanguageInfo("scala", "Scala", "//", ("/*", "*/")),
    "lua": LanguageInfo("lua", "Lua", "--", None),
    "bash": LanguageInfo("bash", "Shell", "#", None),
    "sql": LanguageInfo("sql", "SQL", "--", None),
    "r": LanguageInfo("r", "R", "#", None),
    "perl": LanguageInfo("perl", "Perl", "#", None),
    "haskell": LanguageInfo("haskell", "Haskell", "--", None),
    "elixir": LanguageInfo("elixir", "Elixir", "#", None),
    "dart": LanguageInfo("dart", "Dart", "//", ("/*", "*/")),
    "objc": LanguageInfo("objc", "Objective-C", "//", ("/*", "*/")),
    "vhdl": LanguageInfo("vhdl", "VHDL", "--", None),
    "verilog": LanguageInfo("verilog", "Verilog", "//", ("/*", "*/")),
    "fortran": LanguageInfo("fortran", "Fortran", "!", None),
    "commonlisp": LanguageInfo("commonlisp", "Common Lisp", ";", None),
    "pascal": LanguageInfo("pascal", "Pascal / Delphi", "//", ("{", "}")),
    "vb": LanguageInfo("vb", "Visual Basic", "'", None),
    "ada": LanguageInfo("ada", "Ada", "--", None),
    "erlang": LanguageInfo("erlang", "Erlang", "%", None),
    "powershell": LanguageInfo("powershell", "PowerShell", "#", ("<#", "#>")),
    "tcl": LanguageInfo("tcl", "Tcl", "#", None),
    "cobol": LanguageInfo("cobol", "COBOL", "*", None),
    "groovy": LanguageInfo("groovy", "Groovy", "//", ("/*", "*/")),
}

_EXTENSION_MAP: dict[str, str] = {
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".ipp": "cpp",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sc": "scala",
    ".cs": "csharp",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".py": "python",
    ".pyi": "python",
    ".rb": "ruby",
    ".rake": "ruby",
    ".php": "php",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".r": "r",
    ".R": "r",
    ".go": "go",
    ".rs": "rust",
    ".swift": "swift",
    ".m": "objc",
    ".mm": "objc",
    ".dart": "dart",
    ".hs": "haskell",
    ".ex": "elixir",
    ".exs": "elixir",
    ".lisp": "commonlisp",
    ".cl": "commonlisp",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".sql": "sql",
    ".f": "fortran",
    ".f90": "fortran",
    ".f95": "fortran",
    ".for": "fortran",
    ".vhd": "vhdl",
    ".vhdl": "vhdl",
    ".v": "verilog",
    ".sv": "verilog",
    ".pas": "pascal",
    ".dpr": "pascal",
    ".dfm": "pascal",
    ".lpr": "pascal",
    ".pp": "pascal",
    ".vb": "vb",
    ".bas": "vb",
    ".cls": "vb",
    ".frm": "vb",
    ".ada": "ada",
    ".adb": "ada",
    ".ads": "ada",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".tcl": "tcl",
    ".cob": "cobol",
    ".cbl": "cobol",
    ".cpy": "cobol",
    ".ccp": "cobol",
    ".groovy": "groovy",
    ".gradle": "groovy",
}

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(_EXTENSION_MAP)


def detect_language(path: str) -> LanguageInfo | None:
    """Resolve the language from a path, or None when unsupported."""
    suffix = PurePosixPath(path.replace("\\", "/")).suffix

    if not suffix:
        return None

    key = _EXTENSION_MAP.get(suffix) or _EXTENSION_MAP.get(suffix.lower())

    return LANGUAGES.get(key) if key else None


def is_supported(path: str) -> bool:
    return detect_language(path) is not None


def extensions_by_language() -> dict[str, list[str]]:
    """Extensions grouped by language. Consumed by GET /v1/meta/languages."""
    grouped: dict[str, list[str]] = {}

    for extension, language_key in _EXTENSION_MAP.items():
        grouped.setdefault(language_key, []).append(extension)

    return {key: sorted(values) for key, values in grouped.items()}
