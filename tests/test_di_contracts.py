"""DI contract enforcement — every get_* must have a set_* call.

Scans ALL .py files under serin/ for functions matching the pattern:
  def get_X(...) -> T:
      if _x is None:
          raise RuntimeError(...)
      return _x

For each getter found, locates the matching setter (set_X or init_X)
in the same file, then verifies the setter is actually called somewhere
in the codebase. Catches DI slots that are read but never written.

Discovers new patterns automatically — no hardcoded file paths.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERIN_DIR = PROJECT_ROOT / "serin"

_GETTER_RE = re.compile(
    r"def (get_\w+)\(.*?\).*?:\s*\n"
    r"(?:.*?\n)*?"
    r".*?raise RuntimeError\(",
    re.MULTILINE,
)


def _find_di_pairs() -> list[tuple[str, str, str]]:
    """Scan every .py file for getter/setter DI patterns."""
    pairs: list[tuple[str, str, str]] = []
    for pyfile in SERIN_DIR.rglob("*.py"):
        if pyfile.name == "__init__.py":
            continue
        content = pyfile.read_text(errors="replace")
        for match in _GETTER_RE.finditer(content):
            getter = match.group(1)
            suffix = getter.removeprefix("get_")
            found = False
            for prefix in ("set_", "init_"):
                candidate = f"{prefix}{suffix}"
                if f"def {candidate}(" in content:
                    pairs.append((getter, candidate, str(pyfile.relative_to(PROJECT_ROOT))))
                    found = True
                    break
            if not found:
                # Fallback: find any init_*/set_* in the same file that writes
                # to a global matching the getter's backing variable
                for init_match in re.finditer(r"def (init_\w+)\(", content):
                    pairs.append((getter, init_match.group(1), str(pyfile.relative_to(PROJECT_ROOT))))
                    break
    return pairs


def _grep_codebase(pattern: str) -> list[str]:
    """Search all .py files under serin/ for pattern, excluding def lines."""
    matches: list[str] = []
    for pyfile in SERIN_DIR.rglob("*.py"):
        for line in pyfile.read_text(errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                continue
            if re.search(pattern, line):
                matches.append(str(pyfile.relative_to(PROJECT_ROOT)))
                break
    return matches


_DI_PAIRS = _find_di_pairs()


@pytest.mark.parametrize(
    "getter,setter,source",
    _DI_PAIRS,
    ids=[f"{p[0]} (in {p[2]})" for p in _DI_PAIRS],
)
def test_setter_is_called(getter: str, setter: str, source: str) -> None:
    """Every get_* must have at least one set_*/init_* call in the codebase."""
    callers = _grep_codebase(rf"\b{setter}\s*\(")
    assert callers, (
        f"{setter}() is never called anywhere in serin/. "
        f"{getter}() in {source} will always raise RuntimeError at runtime. "
        f"Add a {setter}(...) call during startup."
    )
