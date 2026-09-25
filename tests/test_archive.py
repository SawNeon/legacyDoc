"""Safe zip extraction tests."""

from __future__ import annotations

import random
import zipfile
from pathlib import Path

import pytest
from legacydoc_core.archive import MAX_COMPRESSION_RATIO, looks_like_zip, safe_extract
from legacydoc_core.errors import ValidationError

DEFAULT_LIMITS = {
    "max_files": 100,
    "max_total_bytes": 10 * 1024 * 1024,
    "max_file_bytes": 1024 * 1024,
}

ALLOWED_SUFFIXES = frozenset({".py", ".js", ".cpp", ".go"})


def build_archive(tmp_path: Path, entries: dict[str, bytes], name: str = "upload.zip") -> Path:
    archive_path = tmp_path / name

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry_name, content in entries.items():
            archive.writestr(entry_name, content)

    return archive_path


def extract(archive_path: Path, destination: Path, **overrides):
    return safe_extract(
        archive_path,
        destination,
        **{**DEFAULT_LIMITS, "allowed_suffixes": ALLOWED_SUFFIXES, **overrides},
    )


def test_extracts_source_files(tmp_path):
    archive_path = build_archive(
        tmp_path,
        {
            "project/main.py": b"def run():\n    return 1\n",
            "project/util/helper.js": b"export const add = (a, b) => a + b;\n",
        },
    )
    destination = tmp_path / "out"

    result = extract(archive_path, destination)

    assert result.files_written == 2
    assert (destination / "project/main.py").is_file()
    assert (destination / "project/util/helper.js").is_file()
    assert result.rejected_entries == []


def test_filters_unsupported_extensions_during_extraction(tmp_path):
    archive_path = build_archive(
        tmp_path,
        {
            "app.py": b"x = 1\n",
            "video.mp4": b"\x00" * 5000,
            "photo.png": b"\x00" * 5000,
        },
    )
    destination = tmp_path / "out"

    result = extract(archive_path, destination)

    assert result.files_written == 1
    assert result.skipped_unsupported == 2
    assert not (destination / "video.mp4").exists()


@pytest.mark.parametrize(
    "malicious_name",
    [
        "../outside.py",
        "../../../../etc/cron.d/backdoor.py",
        "project/../../escaped.py",
        "project/subdir/../../../escaped.py",
    ],
)
def test_rejects_directory_traversal(tmp_path, malicious_name):
    archive_path = build_archive(tmp_path, {malicious_name: b"# payload\n", "ok.py": b"x = 1\n"})
    destination = tmp_path / "out"

    result = extract(archive_path, destination)

    assert not (tmp_path / "outside.py").exists()
    assert not (tmp_path / "escaped.py").exists()
    assert any("traversal" in entry for entry in result.rejected_entries)

    for written in (path for path in destination.rglob("*") if path.is_file()):
        assert written.resolve().is_relative_to(destination.resolve())


def test_rejects_absolute_path(tmp_path):
    archive_path = build_archive(tmp_path, {"/tmp/absolute.py": b"x = 1\n", "ok.py": b"y = 2\n"})

    result = extract(archive_path, tmp_path / "out")

    assert any("absolute path" in entry for entry in result.rejected_entries)
    assert result.files_written == 1


def test_rejects_windows_drive_letter(tmp_path):
    archive_path = build_archive(
        tmp_path, {"C:/Windows/System32/evil.py": b"x = 1\n", "ok.py": b"y = 2\n"}
    )

    result = extract(archive_path, tmp_path / "out")

    assert any("drive letter" in entry for entry in result.rejected_entries)


def test_rejects_backslash_traversal(tmp_path):
    """Archives built on Windows may use backslash separators."""
    archive_path = build_archive(tmp_path, {"..\\..\\outside.py": b"x = 1\n", "ok.py": b"y = 2\n"})

    result = extract(archive_path, tmp_path / "out")

    assert not (tmp_path / "outside.py").exists()
    assert any("traversal" in entry for entry in result.rejected_entries)


def test_rejects_bomb_from_declared_size(tmp_path):
    archive_path = tmp_path / "bomb.zip"

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.py", b"\x00" * (20 * 1024 * 1024))

    with pytest.raises(ValidationError, match="descomprimido"):
        extract(archive_path, tmp_path / "out", max_total_bytes=5 * 1024 * 1024)


def test_rejects_suspicious_compression_ratio(tmp_path):
    archive_path = tmp_path / "bomb.zip"

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.py", b"\x00" * (900 * 1024))
        archive.writestr("ok.py", b"x = 1\n")

    result = extract(archive_path, tmp_path / "out")

    assert any("compression ratio" in entry for entry in result.rejected_entries)
    assert result.files_written == 1


def test_real_source_does_not_trigger_ratio_check(tmp_path):
    """Uses project source: synthetic data compresses unrealistically."""
    real_source = Path("packages/agents/legacydoc_agents/pipeline.py").read_bytes()
    archive_path = build_archive(tmp_path, {"pipeline.py": real_source})

    result = extract(archive_path, tmp_path / "out", max_file_bytes=5 * 1024 * 1024)

    assert result.rejected_entries == []
    assert result.files_written == 1


def test_highly_repetitive_source_still_passes(tmp_path):
    """Regression: a 100x limit rejected legitimate generated code at 307x."""
    source = ("def example(a, b):\n    return a + b\n\n" * 4000).encode()
    archive_path = build_archive(tmp_path, {"generated.py": source})

    result = extract(archive_path, tmp_path / "out", max_file_bytes=5 * 1024 * 1024)

    assert result.rejected_entries == []
    assert result.files_written == 1
    assert MAX_COMPRESSION_RATIO > 307


def test_byte_limit_catches_bomb_tuned_below_ratio(tmp_path):
    """A bomb tuned to pass the ratio check still dies on the byte ceiling."""
    archive_path = tmp_path / "sneaky.zip"
    random.seed(7)
    body = "".join(random.choice("abcdefgh ") for _ in range(400_000)).encode()

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.py", body)
        archive.writestr("ok.py", b"x = 1\n")

    result = extract(archive_path, tmp_path / "out", max_file_bytes=50_000)

    assert result.skipped_unsupported == 1
    assert result.files_written == 1
    assert not (tmp_path / "out" / "large.py").exists()


def test_rejects_too_many_entries(tmp_path):
    archive_path = build_archive(tmp_path, {f"file_{i}.py": b"x = 1\n" for i in range(60)})

    with pytest.raises(ValidationError, match="entradas"):
        extract(archive_path, tmp_path / "out", max_files=50)


def test_skips_oversized_individual_file(tmp_path):
    archive_path = build_archive(
        tmp_path,
        {"huge.py": ("a = 1\n" * 200_000).encode(), "small.py": b"x = 1\n"},
    )

    result = extract(archive_path, tmp_path / "out", max_file_bytes=1000)

    assert result.files_written == 1
    assert result.skipped_unsupported == 1


def test_rejects_invalid_archive(tmp_path):
    invalid = tmp_path / "fake.zip"
    invalid.write_bytes(b"definitely not a zip file")

    with pytest.raises(ValidationError, match="nao e um .zip valido"):
        extract(invalid, tmp_path / "out")


def test_rejects_archive_without_supported_code(tmp_path):
    archive_path = build_archive(tmp_path, {"readme.txt": b"nothing", "photo.png": b"\x00" * 100})

    with pytest.raises(ValidationError, match="Nenhum arquivo de codigo"):
        extract(archive_path, tmp_path / "out")


def test_zip_signature_detection():
    assert looks_like_zip(b"PK\x03\x04rest")
    assert looks_like_zip(b"PK\x05\x06")
    assert not looks_like_zip(b"%PDF-1.4")
    assert not looks_like_zip(b"")
    assert not looks_like_zip(b"<?php system($_GET[0]); ?>")


def test_directory_entries_do_not_create_files(tmp_path):
    archive_path = tmp_path / "with_dir.zip"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("project/", b"")
        archive.writestr("project/app.py", b"x = 1\n")

    result = extract(archive_path, tmp_path / "out")

    assert result.files_written == 1
