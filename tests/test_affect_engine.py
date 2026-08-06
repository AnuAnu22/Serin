"""Tests for UserAffectEngine: decay, valence updates, familiarity, snapshot cache."""
import math
import time
from typing import Any
from unittest.mock import MagicMock

import pytest


def _make_engine(rows: dict[str, dict[str, Any]] | None = None) -> Any:
    """Build a UserAffectEngine with a fake in-memory store."""
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        UserAffectEngine,
    )

    store = MagicMock()
    engine = UserAffectEngine(store)
    # Pre-populate cache if rows given
    if rows:
        from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
            AffectSnapshot,
        )
        for uid, data in rows.items():
            engine._cache[uid] = AffectSnapshot(
                valence=data.get("valence", 0.0),
                familiarity=data.get("familiarity", 0.0),
                impression=data.get("impression"),
            )
    return engine


# ── Decay math ────────────────────────────────────────────────────────────────

def test_decay_half_life_exactness() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        DECAY_HALF_LIFE_S,
        _decayed_valence,
    )
    v = 1.0
    now = time.time()
    result = _decayed_valence(v, now - DECAY_HALF_LIFE_S, now)
    assert abs(result - 0.5) < 1e-9


def test_decay_identity_at_zero_elapsed() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        _decayed_valence,
    )
    now = time.time()
    assert _decayed_valence(0.8, now, now) == pytest.approx(0.8)


def test_decay_sign_preserving() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        _decayed_valence,
    )
    now = time.time()
    assert _decayed_valence(-0.6, now - 3600, now) < 0


def test_decay_monotonic_toward_zero() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        _decayed_valence,
    )
    now = time.time()
    v0 = 0.8
    v1 = _decayed_valence(v0, now - 3600, now)
    v2 = _decayed_valence(v0, now - 7200, now)
    assert v1 > v2 > 0


# ── Valence update rule ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_user_starts_at_neutral() -> None:
    engine = _make_engine()
    snap = engine.snapshot_cached("brand_new_user")
    assert snap.valence == 0.0


@pytest.mark.asyncio
async def test_record_sentiment_increments_familiarity() -> None:
    engine = _make_engine()
    await engine.record_sentiment("u1", 0.5)
    await engine.record_sentiment("u1", 0.5)
    snap = engine.snapshot_cached("u1")
    assert snap.familiarity > 0.0


@pytest.mark.asyncio
async def test_positive_sentiment_raises_valence() -> None:
    engine = _make_engine()
    await engine.record_sentiment("u1", 1.0)
    snap = engine.snapshot_cached("u1")
    assert snap.valence > 0.0


@pytest.mark.asyncio
async def test_negative_sentiment_lowers_valence() -> None:
    engine = _make_engine()
    await engine.record_sentiment("u1", -1.0)
    snap = engine.snapshot_cached("u1")
    assert snap.valence < 0.0


@pytest.mark.asyncio
async def test_valence_clamped_at_plus_one() -> None:
    engine = _make_engine()
    for _ in range(30):
        await engine.record_sentiment("u1", 1.0)
    snap = engine.snapshot_cached("u1")
    assert snap.valence <= 1.0


@pytest.mark.asyncio
async def test_valence_clamped_at_minus_one() -> None:
    engine = _make_engine()
    for _ in range(30):
        await engine.record_sentiment("u1", -1.0)
    snap = engine.snapshot_cached("u1")
    assert snap.valence >= -1.0


# ── Familiarity ───────────────────────────────────────────────────────────────

def test_familiarity_zero_at_zero_messages() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        _familiarity,
    )
    assert _familiarity(0) == 0.0


def test_familiarity_bounded_below_one() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        _familiarity,
    )
    # At 500 messages: 1 - exp(-10) ≈ 0.99995, well below 1 in float64
    assert _familiarity(500) < 1.0


def test_familiarity_monotonic() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        _familiarity,
    )
    assert _familiarity(10) < _familiarity(50) < _familiarity(150)


def test_familiarity_50_messages_approx_063() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        _familiarity,
    )
    assert abs(_familiarity(50) - (1 - math.exp(-1.0))) < 0.01


# ── snapshot_cached neutral miss ─────────────────────────────────────────────

def test_snapshot_cached_returns_neutral_on_miss() -> None:
    engine = _make_engine()
    snap = engine.snapshot_cached("never_seen")
    assert snap.valence == 0.0
    assert snap.familiarity == 0.0
    assert snap.impression is None


def test_snapshot_cached_returns_cached_value() -> None:
    engine = _make_engine(rows={"u1": {"valence": 0.7, "familiarity": 0.3, "impression": "nice"}})
    snap = engine.snapshot_cached("u1")
    assert snap.valence == pytest.approx(0.7)
    assert snap.impression == "nice"


# ── impression application ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_impression_updates_cache() -> None:
    engine = _make_engine()
    await engine.record_sentiment("u1", 0.5)
    await engine.apply_impression("u1", text="they're kind", delta=0.1)
    snap = engine.snapshot_cached("u1")
    assert snap.impression == "they're kind"
    assert snap.valence > 0.0


@pytest.mark.asyncio
async def test_apply_impression_clamps_delta() -> None:
    engine = _make_engine(rows={"u1": {"valence": 0.9}})
    await engine.apply_impression("u1", text="great", delta=0.5)  # delta > 0.2
    snap = engine.snapshot_cached("u1")
    assert snap.valence <= 1.0


# ── parse_impression ──────────────────────────────────────────────────────────

def test_parse_impression_valid_json() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        UserAffectEngine,
    )
    raw = '{"impression": "pretty friendly", "valence_delta": 0.1}'
    result = UserAffectEngine.parse_impression(raw)
    assert result is not None
    text, delta = result
    assert text == "pretty friendly"
    assert delta == pytest.approx(0.1)


def test_parse_impression_garbage_returns_none() -> None:
    from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
        UserAffectEngine,
    )
    assert UserAffectEngine.parse_impression("not json at all") is None
    assert UserAffectEngine.parse_impression("{}") is None
