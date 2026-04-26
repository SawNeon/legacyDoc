# tools/github_loader.py
import os
import shutil
import stat
import uuid

from git import Repo

def remove_readonly(func, path, _):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def load_cpp_from_github(repo_url: str, target_dir: str = "./cloned_repo") -> dict:
    unique_id = uuid.uuid4().hex[:8]
    session_dir = f"{target_dir}_{unique_id}"

    print(f": Cloning repository {repo_url}...")

    if os.path.exists(session_dir):
        print(f"🧹 Cleaning up existing directory...")
        try:
            shutil.rmtree(session_dir, onerror=remove_readonly)  # Python <= 3.11
        except TypeError:
            shutil.rmtree(session_dir, onexc=remove_readonly)

    Repo.clone_from(repo_url, session_dir)
    print("✅ Clone completo! scanning files C/C++...")

    cpp_files = {}

    for root, dirs, files in os.walk(session_dir):
        for file in files:
            if file.endswith((".cpp", ".hpp", ".h", ".c")):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        relative_path = os.path.relpath(full_path, session_dir)
                        cpp_files[relative_path] = content
                except Exception as e:
                    print(f"⚠️ [GitHub Loader]: Erro ao ler {file}: {e}")

    try:
        shutil.rmtree(session_dir, onerror=remove_readonly)
    except TypeError:
        shutil.rmtree(session_dir, onexc=remove_readonly)
    except Exception as e:
        print(f"⚠️ [GitHub Loader]: Warning - We were unable to delete the temporary folder: {e}")

    return cpp_files