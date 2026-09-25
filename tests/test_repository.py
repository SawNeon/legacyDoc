"""Repository loading: the step between a URL and something the parser can read."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from legacydoc_core.errors import ValidationError
from legacydoc_core.repository import (
    RepositoryLoader,
    cleanup_directory,
    validate_repo_url,
)

CODE = "def somar(a, b):\n    return a + b\n"


def _loader(
    tmp_path: Path,
    *,
    max_file_bytes: int = 512 * 1024,
    max_files: int = 2000,
    max_total_bytes: int = 250 * 1024 * 1024,
) -> RepositoryLoader:
    return RepositoryLoader(
        tmp_root=tmp_path / "tmp",
        max_file_bytes=max_file_bytes,
        max_files=max_files,
        max_total_bytes=max_total_bytes,
        clone_timeout_seconds=30,
    )


def _write(root: Path, relative: str, content: str | bytes = CODE) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")

    return path


async def test_scan_collects_supported_sources(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "src/app.py")
    _write(repo, "src/util.js", "export const x = 1;\n")

    scan = await _loader(tmp_path).scan(repo)

    assert {file.path for file in scan.files} == {"src/app.py", "src/util.js"}
    assert {file.language for file in scan.files} == {"python", "javascript"}


async def test_scan_ignores_dependency_and_build_directories(tmp_path):
    """A vendored dependency is not the customer's legacy code."""
    repo = tmp_path / "repo"
    _write(repo, "src/app.py")
    _write(repo, "node_modules/lib/index.js", "module.exports = 1;\n")
    _write(repo, "build/out.py")
    _write(repo, ".venv/lib/site.py")

    scan = await _loader(tmp_path).scan(repo)

    assert [file.path for file in scan.files] == ["src/app.py"]


async def test_scan_ignores_generated_and_minified_files(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "src/app.py")
    _write(repo, "static/jquery.min.js", "var a=1;\n")
    _write(repo, "proto/order_pb2.py")

    scan = await _loader(tmp_path).scan(repo)

    assert [file.path for file in scan.files] == ["src/app.py"]


async def test_scan_skips_files_over_the_size_ceiling(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "src/small.py")
    _write(repo, "src/huge.py", "x = 1\n" * 5000)

    scan = await _loader(tmp_path, max_file_bytes=200).scan(repo)

    assert [file.path for file in scan.files] == ["src/small.py"]
    assert scan.skipped_too_large == 1


async def test_scan_stops_at_the_file_ceiling_and_says_so(tmp_path):
    """The plan ceiling is applied later; this one protects the server."""
    repo = tmp_path / "repo"

    for index in range(10):
        _write(repo, f"src/mod_{index}.py")

    scan = await _loader(tmp_path, max_files=4).scan(repo)

    assert len(scan.files) == 4
    assert scan.truncated is True


async def test_scan_stops_at_the_total_size_ceiling(tmp_path):
    repo = tmp_path / "repo"

    for index in range(10):
        _write(repo, f"src/mod_{index}.py", "x = 1\n" * 100)

    scan = await _loader(tmp_path, max_total_bytes=900).scan(repo)

    assert scan.truncated is True
    assert len(scan.files) < 10


async def test_scan_counts_undecodable_files_instead_of_crashing(tmp_path):
    """A .py holding latin-1 bytes is common in genuinely legacy code."""
    repo = tmp_path / "repo"
    _write(repo, "src/app.py")
    _write(repo, "src/legado.py", b"# comentario com acento invalido: \xff\xfe\n")

    scan = await _loader(tmp_path).scan(repo)

    assert [file.path for file in scan.files] == ["src/app.py"]
    assert scan.skipped_binary == 1


async def test_scan_skips_empty_files(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "src/app.py")
    _write(repo, "src/__init__.py", "\n   \n")

    scan = await _loader(tmp_path).scan(repo)

    assert [file.path for file in scan.files] == ["src/app.py"]


async def test_scan_honours_an_explicit_path_list(tmp_path):
    """This is what a customer documenting three files of a large repo sends."""
    repo = tmp_path / "repo"
    _write(repo, "src/app.py")
    _write(repo, "src/other.py")

    scan = await _loader(tmp_path).scan(repo, only_paths=["src/app.py"])

    assert [file.path for file in scan.files] == ["src/app.py"]


async def test_scan_hashes_content_so_unchanged_files_can_be_skipped(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "a.py")
    _write(repo, "b.py")

    scan = await _loader(tmp_path).scan(repo)

    assert len({file.sha256 for file in scan.files}) == 1, "identical content, identical hash"
    assert all(len(file.sha256) == 64 for file in scan.files)


async def test_scanning_a_repository_without_code_returns_empty(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "README.md", "# leia\n")

    scan = await _loader(tmp_path).scan(repo)

    assert scan.files == []
    assert scan.total_files_seen == 0


def test_cleanup_removes_read_only_files(tmp_path):
    """Git marks objects read-only on Windows and plain rmtree fails on them."""
    repo = tmp_path / "repo"
    target = _write(repo, "objects/pack.idx", "conteudo\n")
    os.chmod(target, 0o444)

    cleanup_directory(repo)

    assert not repo.exists()


def test_cleanup_of_a_missing_directory_is_not_an_error(tmp_path):
    cleanup_directory(tmp_path / "nunca-existiu")


@pytest.mark.parametrize(
    "repo_url",
    [
        "file:///etc/passwd",
        "git://github.com/owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "https://evil.example.com/owner/repo.git",
        "https://user:senha@github.com/owner/repo.git",
        "https://github.com/",
    ],
)
def test_dangerous_urls_are_refused(repo_url):
    with pytest.raises(ValidationError):
        validate_repo_url(repo_url)


def test_known_hosts_are_accepted():
    for host in ("github.com", "gitlab.com", "bitbucket.org"):
        validate_repo_url(f"https://{host}/owner/repo.git")


async def test_clone_refuses_a_bad_url_before_touching_disk(tmp_path):
    loader = _loader(tmp_path)

    with pytest.raises(ValidationError):
        await loader.clone("file:///etc/passwd")

    assert not (tmp_path / "tmp").exists(), "nothing should be created for a rejected URL"


CLONE_TEST_URL = os.environ.get("CLONE_TEST_REPO_URL", "")

needs_network = pytest.mark.skipif(
    not CLONE_TEST_URL,
    reason="Defina CLONE_TEST_REPO_URL para exercitar o clone de verdade.",
)


@needs_network
async def test_a_real_clone_produces_scannable_files(tmp_path):
    """The only test that proves git, the network and the walk work together."""
    loader = _loader(tmp_path)
    clone_dir = await loader.clone(CLONE_TEST_URL)

    try:
        assert clone_dir.is_dir()

        scan = await loader.scan(clone_dir)

        assert scan.files, "um repositorio de codigo tem de render arquivos"
        assert all(file.content.strip() for file in scan.files)
    finally:
        cleanup_directory(clone_dir)
