"""Runtime integrity — every module under serin/ must import, and
no file may contain undefined variables in string literals.

Two layers of defense:
  1. Import test: every .py file loads without errors
  2. Undefined var scan: Rust binary finds {identifier} in non-f-strings
     where the identifier doesn't exist anywhere in the file
"""
from __future__ import annotations

import asyncio
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERIN_DIR = PROJECT_ROOT / "serin"
SCANNER_BIN = PROJECT_ROOT / "scripts" / "undef-var-scanner" / "target" / "release" / "undef-var-scanner"


# ── Layer 1: Module import ──────────────────────────────────────────────

def _discover_modules() -> list[str]:
    modules: list[str] = []
    for pyfile in sorted(SERIN_DIR.rglob("*.py")):
        if pyfile.name in ("__init__.py", "__main__.py"):
            continue
        rel = pyfile.relative_to(PROJECT_ROOT)
        modules.append(str(rel.with_suffix("")).replace("/", "."))
    return modules


_ALL_SERIN_MODULES = _discover_modules()


@pytest.mark.parametrize("module_name", _ALL_SERIN_MODULES)
def test_module_imports_cleanly(module_name: str) -> None:
    importlib.import_module(module_name)


# ── Layer 2: Undefined variable scan (Rust binary) ─────────────────────

def _run_scanner() -> tuple[int, str]:
    """Run the Rust scanner and return (exit_code, stderr)."""
    if not SCANNER_BIN.exists():
        pytest.skip("Rust scanner not built — run: cargo build --release in scripts/undef-var-scanner/")
    result = subprocess.run(
        [str(SCANNER_BIN), str(SERIN_DIR)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stderr


def _parse_scanner_output(stderr: str) -> list[tuple[str, int, str]]:
    """Parse scanner output into (file, line, varname) tuples."""
    issues: list[tuple[str, int, str]] = []
    for line in stderr.splitlines():
        line = line.strip()
        if " — {" in line and " not defined" in line:
            # Format: "file.py:42 — {varname} not defined"
            parts = line.split(" — ")
            if len(parts) == 2:
                file_line = parts[0]
                var_part = parts[1].replace(" not defined", "").strip("{}")
                if ":" in file_line:
                    filepath, lineno = file_line.rsplit(":", 1)
                    issues.append((filepath, int(lineno), var_part))
    return issues


_UNDEFINED_SCAN = _run_scanner()
_UNDEFINED_ISSUES = _parse_scanner_output(_UNDEFINED_SCAN[1]) if _UNDEFINED_SCAN[0] != 0 else []


@pytest.mark.parametrize(
    "filename,line,varname",
    _UNDEFINED_ISSUES,
    ids=[f"{i[0]}:{i[1]} {{{i[2]}}}" for i in _UNDEFINED_ISSUES],
)
def test_string_var_defined(filename: str, line: int, varname: str) -> None:
    filepath = SERIN_DIR / filename
    source = filepath.read_text(errors="replace")
    lines = source.splitlines()
    context = lines[line - 1].strip() if line <= len(lines) else ""
    assert False, (
        f"{{{varname}}} in {filename}:{line} — "
        f"variable '{varname}' not found in file. Line: {context}"
    )


def test_undefined_scan_runs() -> None:
    """The Rust scanner must execute and report results."""
    exit_code, stderr = _run_scanner()
    # Exit 0 = clean, exit 1 = issues found — both are valid
    # Exit 2+ = scanner crashed
    assert exit_code <= 1, f"Scanner crashed with exit code {exit_code}:\n{stderr}"


def test_voice_available() -> None:
    from serin.d1_2_gateway_io.discord.bot import voice_available
    assert voice_available is True
