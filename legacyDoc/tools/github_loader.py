# tools/github_loader.py
import os
import shutil
from git import Repo


def load_cpp_from_github(repo_url: str, target_dir: str = "./cloned_repo") -> dict:

    print(f"📥 [GitHub Loader]: Cloning repository {repo_url}...")

    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)

    Repo.clone_from(repo_url, target_dir)
    print("✅ [GitHub Loader]: Clone complete! Scanning for C++ files...")

    cpp_files = {}

    for root, dirs, files in os.walk(target_dir):
        for file in files:
            if file.endswith((".cpp", ".hpp", ".h", ".c")):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()

                        relative_path = os.path.relpath(full_path, target_dir)
                        cpp_files[relative_path] = content
                except Exception as e:
                    print(f"⚠️ [GitHub Loader]: Error reading {file}: {e}")

    print(f"📄 [GitHub Loader]: Found {len(cpp_files)} C/C++ files.")
    return cpp_files