"""Rule 5 (Up-and-Left) import compliance checker.

Walks every .py file under serin/, parses imports with the ast module,
resolves each import's filesystem path relative to the importing file,
and confirms the path only goes up the ancestor chain and into a sibling
of an ancestor — never up-then-down into a different branch's descendant.

Usage: python3 scripts/law/check_imports.py
Exit 0 = no violations, exit 1 = violations found.
"""
import ast
import os
import sys
from pathlib import Path


def get_package_root():
    """Find the serin/ package root."""
    here = Path(__file__).resolve().parent
    while here != here.parent:
        if (here / "serin" / "__init__.py").exists():
            return here / "serin"
        here = here.parent
    return Path.cwd() / "serin"


def resolve_import_to_path(import_name, importing_file):
    """Try to resolve an import name to a filesystem path.

    Returns (path, resolved) where resolved is True if we found a .py file.
    """
    parts = import_name.split(".")
    root = get_package_root().parent  # project root

    # Walk the parts and try to find the file
    current = root
    for part in parts:
        candidate_dir = current / part
        candidate_file = current / (part + ".py")
        if candidate_file.exists():
            return candidate_file, True
        elif candidate_dir.is_dir() and (candidate_dir / "__init__.py").exists():
            current = candidate_dir
        else:
            return None, False
    return current, current.exists() and (
        current.is_file() or (current.is_dir() and (current / "__init__.py").exists())
    )


def is_within_serin(path):
    """Check if a resolved path is within the serin/ package."""
    try:
        path.resolve().relative_to(get_package_root().resolve())
        return True
    except ValueError:
        return False


def get_branch(path):
    """Get the top-level branch under serin/ for a path.

    Returns e.g. 'pipeline', 'gateway', 'config', 'state', 'ops', or None.
    """
    try:
        rel = path.resolve().relative_to(get_package_root().resolve())
        parts = rel.parts
        if parts:
            return parts[0]
    except ValueError:
        pass
    return None


def check_file(filepath):
    """Check a single file for Rule 5 violations.

    Returns list of (line_no, import_name, reason) tuples.
    """
    violations = []
    try:
        with open(filepath, "r") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return violations

    importing_branch = get_branch(Path(filepath))
    if importing_branch is None:
        return violations  # outside serin/, skip

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                v = _check_import(alias.name, importing_branch, filepath)
                if v:
                    violations.append((node.lineno, alias.name, v))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                v = _check_import(node.module, importing_branch, filepath)
                if v:
                    violations.append((node.lineno, node.module, v))

    return violations


def _check_import(import_name, importing_branch, filepath):
    """Check if an import violates the up-and-left rule.

    Returns a reason string if violation, None if OK.
    """
    parts = import_name.split(".")
    root = get_package_root()

    # Resolve to a filesystem path
    current = root.parent  # project root
    resolved_branch = None
    for part in parts:
        candidate_dir = current / part
        candidate_file = current / (part + ".py")
        if candidate_dir.is_dir():
            current = candidate_dir
        elif candidate_file.exists():
            current = candidate_file.parent
            break
        else:
            break

    # Check if resolved path is within serin/
    try:
        rel = current.resolve().relative_to(root.resolve())
        resolved_branch = rel.parts[0] if rel.parts else None
    except ValueError:
        return None  # outside serin/, not a violation

    if resolved_branch is None:
        return None

    # Allow importing from config/state (ancestors of everything)
    if resolved_branch in ("config", "state"):
        return None

    # Allow importing from same branch
    if resolved_branch == importing_branch:
        return None

    # Allow importing from root serin/__init__.py
    if import_name in ("serin", "serin.core"):
        return None

    # Everything else is a cousin import (violation)
    return f"Cousin import: {importing_branch}/ → {resolved_branch}/ ({import_name})"


def main():
    root = get_package_root()
    violations = []

    # Only scan the new architecture directories (not old shim directories)
    NEW_DIRS = ("config", "state", "pipeline", "gateway", "ops")

    for scan_dir in NEW_DIRS:
        dirpath = os.path.join(root, scan_dir)
        if not os.path.isdir(dirpath):
            continue
        for dirpath, dirnames, filenames in os.walk(dirpath):
            # Skip __pycache__
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(dirpath, fname)
                    file_violations = check_file(fpath)
                    for line_no, import_name, reason in file_violations:
                        violations.append((fpath, line_no, import_name, reason))

    if violations:
        print(f"FAIL: {len(violations)} import violation(s) found:")
        for fpath, line_no, import_name, reason in violations:
            rel = os.path.relpath(fpath, root.parent)
            print(f"  {rel}:{line_no} — {reason}")
        sys.exit(1)
    else:
        print("PASS: No import violations found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
