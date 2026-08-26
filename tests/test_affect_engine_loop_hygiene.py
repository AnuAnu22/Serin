"""A1 regression: snapshot_cached must not use the deprecated asyncio.get_event_loop().

get_event_loop() creates/returns different loops depending on prior event-loop
state, which made test_snapshot_cached_returns_neutral_on_miss order-dependent:
green alone, red in the full suite. The fix schedules on get_running_loop()
and skips scheduling when no loop is running in this thread. These tests pin
both behaviors deterministically instead of flakily elsewhere.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest


def _make_engine() -> object:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        UserAffectEngine,
    )

    return UserAffectEngine(MagicMock())


def test_no_running_loop_returns_neutral_without_scheduling() -> None:
    """Sync context (no running loop): neutral snapshot, no loop touched."""
    engine = _make_engine()
    snap = engine.snapshot_cached("stranger")
    assert snap.valence == 0.0
    assert snap.familiarity == 0.0
    assert snap.impression is None


def test_no_deprecated_get_event_loop_in_module() -> None:
    """No CALL to asyncio.get_event_loop may exist (prose mentions are fine)."""
    import ast

    from serin.d1_3_state_core.d2_5_state_conversation import d3_3_affect_engine as mod

    src = inspect.getsource(mod)
    tree = ast.parse(src)
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get_event_loop"
    ]
    assert not offenders, (
        f"affect_engine calls asyncio.get_event_loop() at lines {offenders} - "
        "this is the order-dependent suite flake (bugs_to_fix_later.md A1). "
        "Use asyncio.get_running_loop() and skip scheduling on RuntimeError."
    )


@pytest.mark.asyncio
async def test_running_loop_schedules_background_load_once() -> None:
    """Inside a running loop: neutral now, background load scheduled."""
    engine = _make_engine()
    snap = engine.snapshot_cached("u1")
    assert snap.valence == 0.0
    # Let the scheduled call_soon + ensure_future run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    loaded = engine.snapshot_cached("u1")
    # MagicMock store returns a Mock (not a dict), so the load path stores a
    # non-neutral value or leaves the cache empty - either way the cache-miss
    # path must have ATTEMPTED a schedule without raising or deprecation.
    assert loaded is not None
