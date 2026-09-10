"""Terminal output helpers shared by the command line tools."""

from __future__ import annotations

import sys


class Style:
    """ANSI colors, disabled when output is not a terminal."""

    enabled = sys.stdout.isatty()

    @classmethod
    def _paint(cls, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if cls.enabled else text

    @classmethod
    def success(cls, text: str) -> str:
        return cls._paint("32", text)

    @classmethod
    def failure(cls, text: str) -> str:
        return cls._paint("31", text)

    @classmethod
    def warning(cls, text: str) -> str:
        return cls._paint("33", text)

    @classmethod
    def bold(cls, text: str) -> str:
        return cls._paint("1", text)

    @classmethod
    def dim(cls, text: str) -> str:
        return cls._paint("90", text)


def section(title: str) -> None:
    print(f"\n{Style.bold(title)}")
    print(Style.dim("-" * len(title)))
