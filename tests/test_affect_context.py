"""Tests for T10 — _affect_context prompt section (valence-driven, neutral by default)."""
from typing import Any

from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
    AffectSnapshot,
)


def _affect_context(snap: Any, username: str) -> str:
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_3_prompt_assembly.d5_2_prompt_helpers import (
        _affect_context as _fn,
    )
    return _fn(snap, username)


_NEUTRAL = AffectSnapshot(valence=0.0, familiarity=0.0, impression=None)


def test_stranger_returns_empty() -> None:
    """familiarity < 0.1 → no section at all (fixes hostile-default bug)."""
    snap = AffectSnapshot(valence=-1.0, familiarity=0.05, impression=None)
    assert _affect_context(snap, "Bob") == ""


def test_new_user_no_familiarity_returns_empty() -> None:
    snap = AffectSnapshot(valence=0.0, familiarity=0.0, impression=None)
    assert _affect_context(snap, "Alice") == ""


def test_loved_user_bucket() -> None:
    snap = AffectSnapshot(valence=0.6, familiarity=0.5, impression=None)
    text = _affect_context(snap, "Rin")
    assert "genuinely like" in text or "light up" in text


def test_warm_user_bucket() -> None:
    snap = AffectSnapshot(valence=0.2, familiarity=0.5, impression=None)
    text = _affect_context(snap, "Rin")
    assert "warm" in text


def test_neutral_user_bucket() -> None:
    snap = AffectSnapshot(valence=0.0, familiarity=0.5, impression=None)
    text = _affect_context(snap, "Rin")
    assert "neutral" in text


def test_wary_user_bucket() -> None:
    snap = AffectSnapshot(valence=-0.2, familiarity=0.5, impression=None)
    text = _affect_context(snap, "Rin")
    assert "wary" in text


def test_disliked_user_bucket() -> None:
    snap = AffectSnapshot(valence=-0.6, familiarity=0.5, impression=None)
    text = _affect_context(snap, "Rin")
    assert "grating" in text or "curt" in text


def test_impression_appended_when_present() -> None:
    snap = AffectSnapshot(valence=0.2, familiarity=0.5, impression="very kind and funny")
    text = _affect_context(snap, "Rin")
    assert "very kind and funny" in text


def test_no_impression_no_extra_text() -> None:
    snap = AffectSnapshot(valence=0.2, familiarity=0.5, impression=None)
    text = _affect_context(snap, "Rin")
    assert "Your current impression" not in text


def test_boundary_valence_51_is_loved() -> None:
    snap = AffectSnapshot(valence=0.51, familiarity=0.5, impression=None)
    text = _affect_context(snap, "Rin")
    assert "genuinely like" in text or "light up" in text


def test_boundary_valence_minus_51_is_grating() -> None:
    snap = AffectSnapshot(valence=-0.51, familiarity=0.5, impression=None)
    text = _affect_context(snap, "Rin")
    assert "grating" in text or "curt" in text


def test_boundary_familiarity_09_is_empty() -> None:
    snap = AffectSnapshot(valence=1.0, familiarity=0.09, impression=None)
    assert _affect_context(snap, "Rin") == ""


def test_boundary_familiarity_11_is_not_empty() -> None:
    snap = AffectSnapshot(valence=0.0, familiarity=0.11, impression=None)
    assert _affect_context(snap, "Rin") != ""
