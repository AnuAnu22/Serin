#!/usr/bin/env python3
"""Enforce Rules 1, 2, 3: 5/5 Horizon, 500-line Ceiling, Depth-Sequence Coordinate.

Transitional: Rules 1-2 are hard fails. Rule 3 (coordinates) is a warning
until the subdirectory rename pass is complete.
"""
from __future__ import annotations

import fnmatch
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERIN = os.path.join(PROJECT, "serin")

EXEMPT_FILES: set[str] = {"__init__.py", "__main__.py"}
EXEMPT_ROOT: set[str] = {"discord_bot.py", "hot_reloader.py"}

errors: list[str] = []
warnings: list[str] = []


def check_55() -> None:
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "logs")]
        py_files = [f for f in files if f.endswith(".py") and f != "__init__.py"]
        actual_dirs = [d for d in dirs if not d.startswith("__")]
        if len(py_files) > 5:
            errors.append(f"RULE 1 FAIL: {root}: {len(py_files)} .py files (max 5)")
        if len(actual_dirs) > 5:
            errors.append(f"RULE 1 FAIL: {root}: {len(actual_dirs)} subdirs (max 5)")


def check_500() -> None:
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "logs")]
        for f in fnmatch.filter(files, "*.py"):
            if f == "__init__.py":
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp, "r") as fh:
                    count = sum(1 for _ in fh)
                if count > 500:
                    errors.append(f"RULE 2 FAIL: {os.path.relpath(fp, PROJECT)}: {count} lines (max 500)")
            except Exception:
                pass


def check_coordinates() -> None:
    import re
    coord_re = re.compile(r"^d\d_\d_\w+_\w+\.py$")
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "logs")]
        for f in files:
            if f.endswith(".py") and f not in EXEMPT_FILES:
                rel_path = os.path.relpath(os.path.join(root, f), PROJECT)
                parts = rel_path.split(os.sep)
                if len(parts) > 1:
                    first_dir = parts[1]
                    if first_dir.startswith("d") and not coord_re.match(f):
                        warnings.append(f"RULE 3 (transitional): {rel_path} — rename to dN_N_name_name.py")


def main() -> int:
    check_55()
    check_500()
    check_coordinates()
    for w in warnings:
        print(w)
    if errors:
        for e in errors:
            print(e)
        return 1
    if not errors and not warnings:
        print("All structure checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
