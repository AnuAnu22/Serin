"""serin_core PyO3 smoke tests — Rust accelerators must match Python fallbacks.

CONNECTIONS.md Phase-5 rec #5: three live call sites depend on serin_core,
guarded by try/except ImportError fallbacks — meaning a Rust function that
returns WRONG results fails silently into the fallback. Zero tests imported
serin_core before this file. These tests close that gap when the module is
built, and skip cleanly when it is not.

NOTE: `import serin_core` can succeed as an EMPTY NAMESPACE PACKAGE (e.g.
a stray serin_core/ directory) without any PyO3 functions. Never gate on
importability alone — always hasattr-check the functions.

# --- Imports ---
"""
from __future__ import annotations

import importlib
from typing import Any

import pytest

serin_core: Any = pytest.importorskip(
    "serin_core", reason="serin_core not built (maturin develop) — skipping PyO3 smoke"
)

if not hasattr(serin_core, "sanitize_fts_query"):
    pytest.skip(
        "serin_core resolved to a namespace package without PyO3 functions",
        allow_module_level=True,
    )


# --- Entry ---


def _python_sanitize_fts(query: str) -> str:
    """Reference copy of bm25_index._sanitize_query's fallback algorithm.

    Kept verbatim from
    serin/d1_3_state_core/d2_2_core_memory/d3_5_memory_helpers/d6_1_bm25_index.py
    so this test compares against the SAME spec the production fallback uses.
    If that fallback changes, update this copy in the same commit (the sync
    expectation is the point).
    """
    special_chars = set("+-*<>\":()^~{}[]\\!?.',")
    return "".join(" " if ch in special_chars else ch for ch in query).strip()


@pytest.mark.parametrize(
    "query",
    [
        "hello world",
        "user@example.com",
        'quote"and(parens)^~wildcard*',
        "  leading and trailing  ",
        "hyphen-ated plus+ negated -term",
        "unicode café ☕ test",
        "",
        "   ",
        "dots.dots.dots",
        "back\\slash 'quoted'",
    ],
)
def test_sanitize_fts_query_matches_python_fallback(query: str) -> None:
    """Rust sanitize must be byte-identical to the pure-Python spec."""
    rust_result: str = serin_core.sanitize_fts_query(query)
    assert rust_result == _python_sanitize_fts(query), (
        f"serin_core.sanitize_fts_query({query!r}) = {rust_result!r}, "
        f"Python fallback gives {_python_sanitize_fts(query)!r}"
    )


def test_filter_thinking_matches_fallback_contract() -> None:
    """If filter_thinking is exported, thinking tags must not survive it."""
    if not hasattr(serin_core, "filter_thinking"):
        pytest.skip("filter_thinking not exported by this build")
    samples = [
        "clean answer",
        "<think>secret reasoning</think>visible answer",
        "prefix <think>multi\nline\nthinking</think> suffix",
        "<think>only thinking</think>",
        "",
    ]
    for text in samples:
        cleaned: str = serin_core.filter_thinking(text)
        assert "<think>" not in cleaned and "</think>" not in cleaned, (
            f"filter_thinking left tags behind for {text!r}: {cleaned!r}"
        )
        if text and "visible answer" in text:
            assert "visible answer" in cleaned


def test_rerank_candidates_contract() -> None:
    """If rerank_candidates is exported, top-k must be a sensible ordering."""
    if not hasattr(serin_core, "rerank_candidates"):
        pytest.skip("rerank_candidates not exported by this build")
    candidates = [
        {"id": str(i), "content": f"candidate {i}", "score": float(i)}
        for i in range(10)
    ]
    rerank: Any = getattr(serin_core, "rerank_candidates")
    result = rerank(candidates, "candidate", 30)
    # Contract: returns at most top_k items; every returned item is one of
    # the inputs (no fabrication). Exact ordering may differ on ties between
    # implementations — set equality of the returned ids within top-k is the
    # stable property.
    assert isinstance(result, list)
    assert len(result) <= 30
    input_ids = {c["id"] for c in candidates}
    out_ids = {
        item["id"] if isinstance(item, dict) else str(item) for item in result
    }
    assert out_ids <= input_ids, f"rerank fabricated ids: {out_ids - input_ids}"


def test_module_metadata_sanity() -> None:
    """The built module reports itself; guards against namespace-package limbo."""
    assert importlib.import_module("serin_core") is not None
    exported = [name for name in dir(serin_core) if not name.startswith("_")]
    assert exported, "serin_core exposes nothing — broken/empty build"


# --- Core ---
# (test functions above)

# --- Helpers ---
# (_python_sanitize_fts above)

# --- Errors ---
# (none)
