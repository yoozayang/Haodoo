#!/usr/bin/env python3
import argparse
import os
import subprocess
from shutil import which

try:
    from opencc import OpenCC
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: opencc-python-reimplemented. "
        "Install it with: pip install opencc-python-reimplemented"
    ) from exc

cc = OpenCC('s2t')

invalid_map = {
    '<': '＜',
    '>': '＞',
    ':': '：',
    '"': '＂',
    '/': '／',
    '\\': '＼',
    '|': '｜',
    '?': '？',
    '*': '＊',
}

reserved = {
    'CON','PRN','AUX','NUL',
    'COM1','COM2','COM3','COM4','COM5','COM6','COM7','COM8','COM9',
    'LPT1','LPT2','LPT3','LPT4','LPT5','LPT6','LPT7','LPT8','LPT9',
}


def normalize_component(name: str) -> str:
    base, ext = os.path.splitext(name)
    base = cc.convert(base)
    ext = cc.convert(ext)
    full = base + ext
    for k, v in invalid_map.items():
        full = full.replace(k, v)
    full = full.rstrip(" .")
    if not full:
        full = "unnamed"
    base_only, ext_only = os.path.splitext(full)
    if base_only.upper() in reserved:
        full = base_only + "_" + ext_only
    return full


def unique_path(path: str, used: set[str]) -> str:
    norm = os.path.normcase(path)
    if norm not in used and not os.path.exists(path):
        used.add(norm)
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = f"{base}_{i}{ext}"
        norm = os.path.normcase(candidate)
        if norm not in used and not os.path.exists(candidate):
            used.add(norm)
            return candidate
        i += 1


def export_repo(repo: str) -> None:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-tree", "-r", "-z", "--name-only", "HEAD"],
        cwd=repo,
        stdout=subprocess.PIPE,
        check=True,
    )
    files = [p for p in res.stdout.split(b"\0") if p]
    used: set[str] = set()
    for raw in files:
        git_path = raw.decode("utf-8", errors="surrogateescape")
        parts = git_path.split("/")
        new_parts = [normalize_component(p) for p in parts]
        rel = os.path.join(*new_parts)
        target = os.path.join(repo, rel)
        target = unique_path(target, used)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        data = subprocess.run(
            ["git", "show", f"HEAD:{git_path}"],
            cwd=repo,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout
        with open(target, "wb") as f:
            f.write(data)


def is_in_git_dir(path: str) -> bool:
    parts = os.path.normpath(path).split(os.sep)
    return any(p.lower() == ".git" for p in parts)


def rename_tree(base: str) -> None:
    for dirpath, dirnames, filenames in os.walk(base, topdown=False):
        if is_in_git_dir(dirpath):
            continue

        used = set(
            os.path.normcase(os.path.join(dirpath, n))
            for n in os.listdir(dirpath)
        )

        for name in filenames:
            old = os.path.join(dirpath, name)
            if is_in_git_dir(old):
                continue
            new_name = normalize_component(name)
            if new_name == name:
                continue
            new = unique_path(os.path.join(dirpath, new_name), used)
            os.rename(old, new)

        if dirpath == base:
            continue
        parent = os.path.dirname(dirpath)
        dir_name = os.path.basename(dirpath)
        new_dir_name = normalize_component(dir_name)
        if new_dir_name != dir_name and not is_in_git_dir(dirpath):
            used_parent = set(
                os.path.normcase(os.path.join(parent, n))
                for n in os.listdir(parent)
            )
            new_dir_path = unique_path(os.path.join(parent, new_dir_name), used_parent)
            os.rename(dirpath, new_dir_path)


def git_available() -> bool:
    return which("git") is not None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert filenames to Traditional Chinese and fix invalid Windows characters.",
    )
    parser.add_argument(
        "--root",
        default=os.getcwd(),
        help="Target root directory to rename (default: current working directory).",
    )
    parser.add_argument(
        "--export-repo",
        default="",
        help="Optional git repo path to export files from HEAD before renaming.",
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if args.export_repo:
        if not git_available():
            print("git not found; skipping export.")
        else:
            repo_path = os.path.abspath(args.export_repo)
            if os.path.isdir(os.path.join(repo_path, ".git")):
                export_repo(repo_path)

    rename_tree(root)
    print("done")


if __name__ == "__main__":
    main()
