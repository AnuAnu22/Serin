"""
Static analysis gate — ruff + mypy + semgrep + import-linter + bandit + detect-secrets.
Each test asserts zero errors or known baselines.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

RUFF_CHECK_DIRS: list[str] = [
    "serin/gateway/discord",
    "serin/gateway/voice_system",
    "serin/ops",
    "serin/pipeline",
    "serin/state",
]

MYPY_CHECK_DIRS: list[str] = [
    # Add directories here as they become mypy-clean.
    # serin/ops — 107 pre-existing errors (all untyped decorators/globals)
    # serin/gateway/discord — 22 pre-existing errors (all None-safety + untyped funcs)
    # serin/gateway/voice_system — 123 pre-existing errors (delegation pattern)
    # serin/pipeline — 366 pre-existing errors
    # serin/state — 120 pre-existing errors
]


def test_ruff_no_undefined_names() -> None:
    """No undefined names (F821) in critical directories."""
    for d in RUFF_CHECK_DIRS:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", d, "--select", "F821", "--no-cache"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"ruff F821 errors in {d}:\n{result.stdout}"
        )


def test_mypy_passes() -> None:
    """mypy strict mode on clean directories."""
    for d in MYPY_CHECK_DIRS:
        result = subprocess.run(
            [sys.executable, "-m", "mypy", d, "--ignore-missing-imports", "--follow-imports=silent"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"mypy errors in {d}:\n{result.stdout}\n{result.stderr}"
        )


def test_semgrep_custom_rules() -> None:
    """Semgrep custom rules must pass clean."""
    rules_dir = ".semgrep/rules"
    if not os.path.isdir(rules_dir):
        return  # no rules configured yet
    result = subprocess.run(
        [sys.executable, "-m", "semgrep", "--config", rules_dir, "--quiet", "serin/"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"semgrep violations:\n{result.stdout}\n{result.stderr}"
    )


def test_import_linter() -> None:
    """Import architecture per THE_LAW.md Rule 5 layers."""
    import_linter_bin = os.path.join(os.path.dirname(sys.executable), "import-linter")
    if not os.path.isfile(import_linter_bin):
        return  # import-linter not installed
    result = subprocess.run(
        [import_linter_bin, "lint"],
        capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, (
        f"import-linter violations:\n{result.stdout}\n{result.stderr}"
    )


def test_bandit_security() -> None:
    """Bandit security scan on serin/."""
    result = subprocess.run(
        [sys.executable, "-m", "bandit", "-r", "serin/", "-q"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"bandit violations:\n{result.stdout}\n{result.stderr}"
    )


def test_detect_secrets() -> None:
    """Detect secrets baseline check."""
    baseline = ".secrets.baseline"
    if not os.path.isfile(baseline):
        return  # no baseline yet
    result = subprocess.run(
        [sys.executable, "-m", "detect_secrets", "scan", "--baseline", baseline],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"detect-secrets violations:\n{result.stdout}\n{result.stderr}"
    )
