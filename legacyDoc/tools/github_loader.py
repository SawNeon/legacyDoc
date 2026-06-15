import os
import shutil
import stat
import uuid
from pathlib import Path
from urllib.parse import urlparse

from git import Repo

ALLOWED_HOSTS = {"github.com", "www.github.com"}
SOURCE_EXTENSIONS = (".cpp", ".hpp", ".h", ".c")
MAX_FILE_BYTES = int(os.getenv("MAX_SOURCE_FILE_BYTES", str(512 * 1024)))


def remove_readonly(func, path, _):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def validate_repo_url(repo_url: str) -> None:
    parsed = urlparse(repo_url)

    if parsed.scheme != "https":
        raise ValueError("Only HTTPS GitHub repository URLs are supported.")

    if parsed.netloc.lower() not in ALLOWED_HOSTS:
        raise ValueError("Only github.com repository URLs are supported.")

    if not parsed.path.strip("/"):
        raise ValueError("Invalid GitHub repository URL.")


def cleanup_session_dir(session_dir: Path) -> None:
    if not session_dir.exists():
        return

    try:
        shutil.rmtree(session_dir, onerror=remove_readonly)
    except TypeError:
        shutil.rmtree(session_dir, onexc=remove_readonly)
    except Exception as exc:
        print(f"[GitHub Loader]: Could not delete temporary folder: {exc}")


def load_cpp_from_github(repo_url: str, target_dir: str = "./cloned_repo") -> dict:
    validate_repo_url(repo_url)

    unique_id = uuid.uuid4().hex[:8]
    session_dir = Path(f"{target_dir}_{unique_id}").resolve()
    session_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"Cloning repository {repo_url}...")

    cleanup_session_dir(session_dir)

    try:
        Repo.clone_from(repo_url, session_dir, multi_options=["--depth=1"])
        print("Clone complete. Scanning C/C++ files...")

        cpp_files = {}

        for root, _, files in os.walk(session_dir):
            for file_name in files:
                if not file_name.endswith(SOURCE_EXTENSIONS):
                    continue

                full_path = Path(root) / file_name

                try:
                    if full_path.stat().st_size > MAX_FILE_BYTES:
                        print(f"[GitHub Loader]: Skipping large file {file_name}")
                        continue

                    content = full_path.read_text(encoding="utf-8")
                    relative_path = os.path.relpath(full_path, session_dir)
                    cpp_files[relative_path] = content
                except UnicodeDecodeError:
                    print(f"[GitHub Loader]: Skipping non UTF-8 file {file_name}")
                except Exception as exc:
                    print(f"[GitHub Loader]: Error reading {file_name}: {exc}")

        return cpp_files
    finally:
        cleanup_session_dir(session_dir)
