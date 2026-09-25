"""Git repository cloning and scanning."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from legacydoc_parsing.languages import detect_language

from legacydoc_core.errors import ValidationError

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset({"github.com", "www.github.com", "gitlab.com", "bitbucket.org"})

IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "vendor",
        "third_party",
        "thirdparty",
        "dist",
        "build",
        "out",
        "target",
        "bin",
        "obj",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".gradle",
        ".idea",
        ".vscode",
        "Pods",
        "bower_components",
        "coverage",
        "site-packages",
    }
)

MINIFIED_MARKERS = (".min.js", ".min.css", ".bundle.js", ".generated.", "_pb2.py", ".pb.go")


@dataclass(frozen=True)
class RepoFile:
    path: str
    content: str
    size_bytes: int
    language: str
    sha256: str


@dataclass
class RepoScan:
    files: list[RepoFile]
    total_files_seen: int
    skipped_too_large: int
    skipped_binary: int
    truncated: bool


def validate_repo_url(repo_url: str) -> None:
    """Reject anything that is not HTTPS to a known hosting provider."""
    parsed = urlparse(repo_url)

    if parsed.scheme != "https":
        raise ValidationError("Somente URLs HTTPS de repositorio sao aceitas.")

    if parsed.netloc.lower() not in ALLOWED_HOSTS:
        raise ValidationError(f"Host nao permitido. Aceitos: {', '.join(sorted(ALLOWED_HOSTS))}.")

    if not parsed.path.strip("/"):
        raise ValidationError("URL de repositorio invalida.")

    if "@" in parsed.netloc:
        raise ValidationError("Nao envie credenciais embutidas na URL.")


def _remove_readonly(func, path, _):
    """Windows marks .git objects read-only; rmtree fails without this."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def cleanup_directory(directory: Path) -> None:
    if not directory.exists():
        return

    try:
        shutil.rmtree(directory, onexc=_remove_readonly)
    except TypeError:
        shutil.rmtree(directory, onerror=_remove_readonly)
    except Exception as exc:
        logger.warning("Nao foi possivel remover %s: %s", directory, exc)


class RepositoryLoader:
    def __init__(
        self,
        *,
        tmp_root: Path,
        max_file_bytes: int,
        max_files: int,
        max_total_bytes: int,
        clone_timeout_seconds: int,
    ) -> None:
        self._tmp_root = tmp_root
        self._max_file_bytes = max_file_bytes
        self._max_files = max_files
        self._max_total_bytes = max_total_bytes
        self._clone_timeout = clone_timeout_seconds

    async def clone(self, repo_url: str, *, branch: str | None = None) -> Path:
        """Shallow clone into a unique directory. The caller owns cleanup."""
        validate_repo_url(repo_url)

        self._tmp_root.mkdir(parents=True, exist_ok=True)
        target = self._tmp_root / f"repo_{uuid.uuid4().hex[:12]}"

        options = ["--depth=1", "--single-branch", "--no-tags"]

        if branch:
            options.append(f"--branch={branch}")

        def _clone() -> None:
            from git import Repo

            Repo.clone_from(repo_url, target, multi_options=options)

        try:
            await asyncio.wait_for(
                asyncio.to_thread(_clone),
                timeout=self._clone_timeout,
            )
        except TimeoutError:
            cleanup_directory(target)
            raise ValidationError(
                f"O clone excedeu {self._clone_timeout}s. O repositorio e grande demais."
            ) from None
        except Exception as exc:
            cleanup_directory(target)
            raise ValidationError(f"Falha ao clonar o repositorio: {exc}") from exc

        return target

    async def scan(self, root: Path, *, only_paths: list[str] | None = None) -> RepoScan:
        """Walk the clone collecting supported source files."""
        return await asyncio.to_thread(self._scan_sync, root, only_paths)

    def _scan_sync(self, root: Path, only_paths: list[str] | None) -> RepoScan:
        wanted = {path.replace("\\", "/") for path in only_paths} if only_paths else None

        files: list[RepoFile] = []
        total_seen = 0
        skipped_large = 0
        skipped_binary = 0
        total_bytes = 0
        truncated = False

        for current_dir, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in IGNORED_DIRECTORIES and not name.startswith(".")
            ]

            for filename in sorted(filenames):
                full_path = Path(current_dir) / filename
                relative = full_path.relative_to(root).as_posix()

                if wanted is not None and relative not in wanted:
                    continue

                language = detect_language(filename)

                if language is None:
                    continue

                if any(marker in filename for marker in MINIFIED_MARKERS):
                    continue

                total_seen += 1

                try:
                    size = full_path.stat().st_size
                except OSError:
                    continue

                if size > self._max_file_bytes:
                    skipped_large += 1
                    continue

                if total_bytes + size > self._max_total_bytes:
                    truncated = True
                    break

                try:
                    content = full_path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    skipped_binary += 1
                    continue

                if not content.strip():
                    continue

                files.append(
                    RepoFile(
                        path=relative,
                        content=content,
                        size_bytes=size,
                        language=language.name,
                        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    )
                )
                total_bytes += size

                if len(files) >= self._max_files:
                    truncated = True
                    break

            if truncated:
                break

        return RepoScan(
            files=files,
            total_files_seen=total_seen,
            skipped_too_large=skipped_large,
            skipped_binary=skipped_binary,
            truncated=truncated,
        )
