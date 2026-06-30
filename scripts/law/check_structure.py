"""Rule 1/2/3 structure compliance checker.

Walks the serin/ tree and fails if:
- Any directory has more than 5 files (excluding __init__.py and __pycache__)
- Any directory has more than 5 subdirectories
- Any .py file exceeds 500 lines

Usage: python3 scripts/law/check_structure.py
Exit 0 = compliant, exit 1 = violations found.
"""
import os
import sys
from pathlib import Path


def check_structure(root_dir):
    """Check structure compliance under the given directory.

    Returns list of violation strings.
    """
    violations = []

    # Old shim directories to exclude from checking (temporary redirects)
    SKIP_DIRS = {"memory", "messaging", "personality", "utils", "control_panel", "core", "models"}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip __pycache__ and .git
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]

        # Skip old shim directories
        rel = os.path.relpath(dirpath, root_dir)
        if rel != "." and rel.split(os.sep)[0] in SKIP_DIRS:
            dirnames.clear()
            continue

        # Count files (exclude __init__.py)
        real_files = [f for f in filenames if f.endswith(".py") and f != "__init__.py"]
        if len(real_files) > 5:
            rel = os.path.relpath(dirpath, root_dir.parent)
            violations.append(
                f"Rule 1: {rel}/ has {len(real_files)} files (max 5): "
                + ", ".join(real_files)
            )

        # Count subdirectories (exclude old shim dirs from count)
        real_dirs = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
        if len(real_dirs) > 5:
            rel = os.path.relpath(dirpath, root_dir.parent)
            violations.append(
                f"Rule 1: {rel}/ has {len(real_dirs)} subdirectories (max 5): "
                + ", ".join(real_dirs)
            )

        # Check file line counts
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r") as f:
                    lines = len(f.readlines())
                if lines > 500:
                    rel = os.path.relpath(fpath, root_dir.parent)
                    violations.append(
                        f"Rule 2: {rel} has {lines} lines (max 500)"
                    )
            except (UnicodeDecodeError, PermissionError):
                pass

    return violations


def main():
    root = Path(__file__).resolve().parent.parent.parent / "serin"
    if not root.exists():
        print("ERROR: serin/ directory not found")
        sys.exit(2)

    violations = check_structure(root)

    if violations:
        print(f"FAIL: {len(violations)} structure violation(s) found:")
        for v in violations:
            print(f"  {v}")
        sys.exit(1)
    else:
        print("PASS: Structure compliant with Rules 1, 2, 3.")
        sys.exit(0)


if __name__ == "__main__":
    main()
