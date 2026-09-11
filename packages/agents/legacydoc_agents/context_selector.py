"""Selection of the project context injected into prompts.

Storing context entries is easy; what changes answer quality is picking the
right ones per file within a token budget. Sending everything is expensive and
dilutes the prompt, sending nothing yields the usual generic documentation.

Criteria in order: a path glob matching the file, lexical overlap between the
entry and the code, and the client-defined weight.

An entry with neither a matching glob nor a single term in common with the file
is dropped, whatever its weight. Weight ranks entries that are relevant; it is
not a way to force an unrelated one into the prompt. Use a "**" glob to say an
entry genuinely applies to every file.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "have",
        "not",
        "are",
        "was",
        "were",
        "int",
        "str",
        "return",
        "void",
        "const",
        "self",
        "para",
        "com",
        "que",
        "uma",
        "dos",
        "das",
        "por",
        "nao",
        "quando",
    }
)


@dataclass(frozen=True)
class ContextCandidate:
    """A context entry from the database, decoupled from the ORM."""

    id: str
    kind: str
    title: str
    content: str
    path_globs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    weight: int = 100


@dataclass(frozen=True)
class ScoredContext:
    candidate: ContextCandidate
    score: float
    matched_by_glob: bool


def _tokenize(text: str) -> set[str]:
    """Split identifiers into words so camelCase and snake_case become terms."""
    words: set[str] = set()

    for match in _WORD.finditer(text):
        raw = match.group(0)

        for part in raw.split("_"):
            for piece in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+", part):
                lowered = piece.lower()
                if len(lowered) > 2 and lowered not in _STOPWORDS:
                    words.add(lowered)

    return words


def select_context(
    candidates: list[ContextCandidate],
    *,
    file_path: str,
    code_sample: str,
    max_chars: int = 4000,
    max_items: int = 6,
) -> list[ContextCandidate]:
    """Return the entries most relevant to this file, within budget."""
    if not candidates:
        return []

    code_terms = _tokenize(f"{file_path}\n{code_sample}")
    scored: list[ScoredContext] = []

    for candidate in candidates:
        matched_glob = _matches_glob(candidate.path_globs, file_path)

        # An explicit glob that does not match is the client saying no.
        if candidate.path_globs and not matched_glob:
            continue

        item_terms = _tokenize(f"{candidate.title} {candidate.content} {' '.join(candidate.tags)}")
        overlap = len(code_terms & item_terms)
        coverage = overlap / max(len(item_terms), 1)

        # Nothing in common with this file and nobody asked for it to be here.
        # Weight alone must not smuggle an entry in: a note about the payroll
        # module sitting in a prompt about stock reservation is noise, and
        # diluting the prompt is what this selection exists to prevent. An
        # entry that really does apply everywhere says so with a "**" glob.
        if not matched_glob and overlap == 0:
            continue

        score = overlap + coverage * 5 + (candidate.weight / 100.0)

        if matched_glob:
            score += 25.0  # Direcionamento explicito vence relevancia lexical.

        scored.append(ScoredContext(candidate, score, matched_glob))

    scored.sort(key=lambda item: item.score, reverse=True)

    selected: list[ContextCandidate] = []
    used_chars = 0

    for entry in scored:
        if len(selected) >= max_items:
            break

        cost = len(entry.candidate.content) + len(entry.candidate.title) + 8

        if used_chars + cost > max_chars:
            continue

        selected.append(entry.candidate)
        used_chars += cost

    return selected


def render_context(items: list[ContextCandidate]) -> str:
    """Format the selected entries for inclusion in the prompt."""
    if not items:
        return ""

    blocks = [f"[{item.kind}] {item.title}\n{item.content.strip()}" for item in items]

    return "\n\n".join(blocks)


def _matches_glob(globs: tuple[str, ...], file_path: str) -> bool:
    if not globs:
        return False

    normalized = file_path.replace("\\", "/")

    return any(fnmatch.fnmatch(normalized, pattern) for pattern in globs)
