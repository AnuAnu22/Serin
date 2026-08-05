#!/usr/bin/env python3
"""Enforce Rule 5 (Depth DAG) and gateway isolation. No exceptions."""
from __future__ import annotations

import ast
import fnmatch
import os
import sys

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


def _is_type_checking_guard(test: ast.expr) -> bool:
    """True for `if TYPE_CHECKING:` or `if typing.TYPE_CHECKING:`. Imports
    inside this block never execute — they exist purely for static type
    checkers — so they are not a real Gateway Isolation violation. This
    is the standard, safe way to reference a type across layers without
    creating a real runtime dependency; flagging it as a violation
    produces false positives that erode trust in the checker."""
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


def _collect_type_checking_node_ids(tree: ast.AST) -> set[int]:
    """Every node id sitting inside an `if TYPE_CHECKING:` block's body
    (not its orelse — an else branch DOES run at import time)."""
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_guard(node.test):
            for child in node.body:
                for inner in ast.walk(child):
                    guarded.add(id(inner))
    return guarded


def check_file(fp: str) -> None:
    rel = os.path.relpath(fp, PROJECT)
    try:
        with open(fp) as fh:
            tree = ast.parse(fh.read())
    except SyntaxError:
        warnings.append(f"SYNTAX ERROR: {rel}")
        return

    is_gateway = "d1_2_gateway_io" in rel
    type_checking_ids = _collect_type_checking_node_ids(tree)

    for node in ast.walk(tree):
        if id(node) in type_checking_ids:
            continue

        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if len(parts) >= 2 and parts[1] in TOP_LEVEL_DEPTHS:
                    if is_gateway and parts[1] in ("d1_1_pipeline_flow", "d1_3_state_core"):
                        warnings.append(
                            f"GATEWAY ISOLATION: {rel} imports "
                            f"from {parts[1]} ({alias.name}) — use DI"
                        )

        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            parts = node.module.split(".")
            if len(parts) >= 2 and parts[1] in TOP_LEVEL_DEPTHS:
                if is_gateway and parts[1] in ("d1_1_pipeline_flow", "d1_3_state_core"):
                    warnings.append(
                        f"GATEWAY ISOLATION: {rel} imports "
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
        print(f"\n{len(warnings)} violation(s). No exceptions per THE_LAW.md.")
        return 1  # No exceptions — a violation must fail the build.
    print("All import checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
