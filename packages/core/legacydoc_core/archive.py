"""Safe extraction of user-uploaded zip archives."""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from legacydoc_core.errors import ValidationError

logger = logging.getLogger(__name__)

MAX_COMPRESSION_RATIO = 500
"""Highest uncompressed/compressed ratio accepted per entry.

Calibrated against measurements: real source code compresses 3x-6x, generated
code with large tables 6x, source with thousands of identical lines 307x, and a
zip bomb of 50 MB of zeros 1029x.

This is defense in depth rather than the primary control. The guarantee comes
from `max_file_bytes` and `max_total_bytes`, counted byte by byte while
writing, so a bomb tuned to 499x is still cut off by them.
"""

RATIO_CHECK_MIN_SIZE_BYTES = 64 * 1024
"""Small files compress erratically and would trip the ratio check."""

SYMLINK_MODE = 0o120000
FILE_TYPE_MASK = 0o170000
READ_BLOCK_BYTES = 64 * 1024

ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


@dataclass
class ExtractionResult:
    root: Path
    files_written: int
    bytes_written: int
    rejected_entries: list[str] = field(default_factory=list)
    skipped_unsupported: int = 0


def looks_like_zip(header: bytes) -> bool:
    """Check the format signature, since the client-supplied content type lies."""
    return header.startswith(ZIP_SIGNATURES)


def _is_symlink(entry: zipfile.ZipInfo) -> bool:
    return (entry.external_attr >> 16) & FILE_TYPE_MASK == SYMLINK_MODE


def _rejection_reason(entry_name: str) -> str | None:
    if not entry_name or entry_name.endswith("/"):
        return None

    normalized = entry_name.replace("\\", "/")

    if normalized.startswith("/"):
        return "absolute path"

    if len(normalized) >= 2 and normalized[1] == ":":
        return "drive letter in path"

    parts = PurePosixPath(normalized).parts

    if ".." in parts:
        return "directory traversal"

    if any("\x00" in part for part in parts):
        return "null byte in name"

    return None


def _has_suspicious_ratio(entry: zipfile.ZipInfo) -> bool:
    return (
        entry.compress_size > 0
        and entry.file_size > RATIO_CHECK_MIN_SIZE_BYTES
        and entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO
    )


def _reject_oversized_manifest(
    entries: list[zipfile.ZipInfo], max_files: int, max_total_bytes: int
) -> None:
    """Reject from the header before decompressing a single byte."""
    if len(entries) > max_files:
        raise ValidationError(f"O .zip tem {len(entries)} entradas; o limite e {max_files}.")

    declared_total = sum(entry.file_size for entry in entries)

    if declared_total > max_total_bytes:
        raise ValidationError(
            f"O conteudo descomprimido declara {declared_total // 1024 // 1024} MB; "
            f"o limite e {max_total_bytes // 1024 // 1024} MB."
        )


def safe_extract(
    archive_path: Path,
    destination: Path,
    *,
    max_files: int,
    max_total_bytes: int,
    max_file_bytes: int,
    allowed_suffixes: frozenset[str] | None = None,
) -> ExtractionResult:
    """Extract an archive, rejecting traversal, bombs, symlinks and oversized entries.

    Filters by `allowed_suffixes` during extraction rather than afterwards, so an
    archive full of unsupported files never reaches disk.
    """
    destination.mkdir(parents=True, exist_ok=True)
    resolved_root = destination.resolve()
    result = ExtractionResult(root=destination, files_written=0, bytes_written=0)

    try:
        archive = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile as error:
        raise ValidationError("O arquivo enviado nao e um .zip valido.") from error

    with archive:
        entries = archive.infolist()
        _reject_oversized_manifest(entries, max_files, max_total_bytes)

        for entry in entries:
            if entry.is_dir():
                continue

            if _is_symlink(entry):
                result.rejected_entries.append(f"{entry.filename}: symbolic link")
                continue

            reason = _rejection_reason(entry.filename)

            if reason is not None:
                logger.warning("Rejected %s in %s: %s", entry.filename, archive_path, reason)
                result.rejected_entries.append(f"{entry.filename}: {reason}")
                continue

            if entry.file_size > max_file_bytes:
                result.skipped_unsupported += 1
                continue

            if _has_suspicious_ratio(entry):
                ratio = int(entry.file_size / entry.compress_size)
                result.rejected_entries.append(
                    f"{entry.filename}: suspicious compression ratio ({ratio}x)"
                )
                continue

            entry_name = entry.filename.replace("\\", "/")

            if (
                allowed_suffixes is not None
                and PurePosixPath(entry_name).suffix.lower() not in allowed_suffixes
            ):
                result.skipped_unsupported += 1
                continue

            target = (destination / entry_name).resolve()

            if not target.is_relative_to(resolved_root):
                result.rejected_entries.append(f"{entry.filename}: escapes destination")
                continue

            _write_entry(
                archive,
                entry,
                target,
                result=result,
                max_file_bytes=max_file_bytes,
                max_total_bytes=max_total_bytes,
            )

    if result.files_written == 0:
        raise ValidationError(
            "Nenhum arquivo de codigo suportado foi encontrado no .zip. "
            "Consulte GET /v1/meta/languages."
        )

    return result


def _write_entry(
    archive: zipfile.ZipFile,
    entry: zipfile.ZipInfo,
    target: Path,
    *,
    result: ExtractionResult,
    max_file_bytes: int,
    max_total_bytes: int,
) -> None:
    """Stream one entry to disk, counting real bytes rather than trusting the header."""
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0

    with archive.open(entry) as source, open(target, "wb") as sink:
        while block := source.read(READ_BLOCK_BYTES):
            written += len(block)

            if written > max_file_bytes:
                sink.close()
                target.unlink(missing_ok=True)
                result.rejected_entries.append(f"{entry.filename}: real size exceeds declared size")
                return

            if result.bytes_written + written > max_total_bytes:
                sink.close()
                target.unlink(missing_ok=True)
                raise ValidationError("O conteudo real do .zip excede o limite total permitido.")

            sink.write(block)

    result.files_written += 1
    result.bytes_written += written
