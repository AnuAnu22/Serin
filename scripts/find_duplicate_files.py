"""AST-based duplicate file detector.

Exits with code 0 if no duplicates, 1 if any found.
Skips __init__.py, __pycache__, .venv/, .git/, node_modules/.
"""
import ast
import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path

IGNORE_DIRS = {"__pycache__", ".venv", ".git", "node_modules", "state"}
IGNORE_FILES = {"__init__.py", "find_duplicate_files.py", "check.sh"}
SRC_DIRS = ["serin", "tests", "scripts"]


def _ast_hash(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text())
        return hashlib.sha256(ast.dump(tree, indent=2).encode()).hexdigest()
    except SyntaxError:
        return ""


def _walk() -> list[Path]:
    files = []
    for d in SRC_DIRS:
        root = Path(d)
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            if any(part in IGNORE_DIRS for part in p.parts):
                continue
            if p.name in IGNORE_FILES:
                continue
            files.append(p)
    return files


def main() -> int:
    hashes: dict[str, list[Path]] = defaultdict(list)
    for f in _walk():
        h = _ast_hash(f)
        if h:
            hashes[h].append(f)

    found = 0
    for h, group in sorted(hashes.items()):
        if len(group) > 1:
            print(f"DUPLICATE ({len(group)} files, hash={h[:12]}):")
            for f in group:
                print(f"  {f}")
            found += 1

    if found:
        print(f"\nERROR: {found} duplicate set(s) found — reject.")
        return 1
    print("OK — no duplicate-content files found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
