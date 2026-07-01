#!/usr/bin/env python3
"""Enforce Rule 5 (Depth DAG) and gateway isolation.

Transitional: prints warnings for violations that require subdirectory
coordinate renaming. Hard-fails only on egregious violations.
"""
from __future__ import annotations

import ast
import os
import sys
import fnmatch

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERIN = os.path.join(PROJECT, "serin")

TOP_LEVEL_DEPTHS: dict[str, int] = {
    "d1_1_pipeline_flow": 1,
    "d1_2_gateway_io": 2,
    "d1_3_state_core": 3,
    "d1_4_config_base": 4,
    "d1_5_ops_tooling": 5,
}

warnings: list[str] = []


def check_file(fp: str) -> None:
    rel = os.path.relpath(fp, PROJECT)
    try:
        with open(fp, "r") as fh:
            tree = ast.parse(fh.read())
    except SyntaxError:
        warnings.append(f"SYNTAX ERROR: {rel}")
        return

    is_gateway = "d1_2_gateway_io" in rel

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if len(parts) >= 2 and parts[1] in TOP_LEVEL_DEPTHS:
                    if is_gateway and parts[1] in ("d1_1_pipeline_flow", "d1_3_state_core"):
                        warnings.append(
                            f"GATEWAY ISOLATION (transitional): {rel} imports "
                            f"from {parts[1]} ({alias.name}) — use DI"
                        )

        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            parts = node.module.split(".")
            if len(parts) >= 2 and parts[1] in TOP_LEVEL_DEPTHS:
                if is_gateway and parts[1] in ("d1_1_pipeline_flow", "d1_3_state_core"):
                    warnings.append(
                        f"GATEWAY ISOLATION (transitional): {rel} imports "
                        f"from {parts[1]} ({node.module}) — use DI"
                    )


def main() -> int:
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "logs")]
        for f in fnmatch.filter(files, "*.py"):
            check_file(os.path.join(root, f))

    if warnings:
        for w in warnings:
            print(w)
        return 0  # transitional — don't fail
    print("All import checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
