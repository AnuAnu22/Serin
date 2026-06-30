"""Find Python files with identical content (whitespace/comments insensitive).

Skips __init__.py (all package markers are expected to be identical) and
files in .venv, .git, __pycache__, node_modules.
"""

import ast
import sys
from pathlib import Path
from collections import defaultdict


def normalize(content: str) -> str:
    """Strip comments and normalize whitespace for comparison."""
    try:
        tree = ast.parse(content)
        return ast.dump(tree, indent=0)
    except SyntaxError:
        return content.strip()


def main(fail_on_match: bool = False) -> int:
    root = Path(__file__).resolve().parent.parent
    hashes: dict[str, list[Path]] = defaultdict(list)

    EXCLUDED_PARTS = {".git", "__pycache__", ".venv", "node_modules"}
    for path in sorted(root.rglob("*.py")):
        if set(path.parts) & EXCLUDED_PARTS:
            continue
        if path.name == "__init__.py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        h = normalize(text)
        hashes[h].append(path)

    duplicates = {k: v for k, v in hashes.items() if len(v) > 1}
    if not duplicates:
        print("No duplicate-content files found.")
        return 0

    print(f"Found {len(duplicates)} duplicate group(s):")
    for h, paths in duplicates.items():
        print(f"\n  {paths[0].relative_to(root)}")
        for p in paths[1:]:
            print(f"    ≡ {p.relative_to(root)}")

    return 1 if fail_on_match else 0


if __name__ == "__main__":
    fail = "--fail-on-match" in sys.argv
    sys.exit(main(fail_on_match=fail))
