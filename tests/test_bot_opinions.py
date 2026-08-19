"""Tests for the bot_opinions opinion system (SERIN_VISION: Serin is biased).

Covers: opinion seeding, real disagreement detection, opinion evolution, and
that opinions flow into the personality context + response planner stance.
"""
from __future__ import annotations

from serin.d1_1_pipeline_flow.d2_3_flow_perceive.d3_2_bot_personality import (
    BotPersonality,
)
from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_4_response_planner import (
    ResponsePlannerStage,
)


def _make_personality(tmp_path) -> BotPersonality:
    db = str(tmp_path / "bot_data.db")
    return BotPersonality(db_path=db)


def test_opinions_seeded_on_init(tmp_path) -> None:
    p = _make_personality(tmp_path)
    assert p.get_opinion("technology") is not None
    assert p.get_opinion("politics")["stance"] == "dislike"
    # No reader path should ever see an empty opinions table now.
    assert p._all_opinion_topics()


def test_can_disagree_is_deterministic_state_comparison(tmp_path) -> None:
    p = _make_personality(tmp_path)
    # The bot loves technology (confident). A user who hates it is a real
    # directional conflict -> disagreement is CAUSED by the state comparison,
    # so it must hold on EVERY call (no die roll, no confidence-scaled chance).
    assert p.can_disagree("technology", "hate") is True
    assert p.can_disagree("technology", "dislike") is True

    # Aligned or one-sided-neutral stances never trigger disagreement.
    assert p.can_disagree("technology", "love") is False
    assert p.can_disagree("technology", "like") is False
    assert p.can_disagree("technology", "neutral") is False


def test_can_disagree_unknown_topic_is_open(tmp_path) -> None:
    p = _make_personality(tmp_path)
    # No stored opinion -> the bot stays open (no manufactured disagreement).
    assert p.can_disagree("some_nonsense_topic", "hate") is False


def test_set_opinion_evolves_state(tmp_path) -> None:
    p = _make_personality(tmp_path)
    before = p.get_opinion("politics")["stance"]
    assert before == "dislike"
    p.set_opinion("politics", "love", "Actually politics can be fascinating.", 0.8)
    after = p.get_opinion("politics")
    assert after["stance"] == "love"
    assert after["confidence"] == 0.8
    assert "fascinating" in after["opinion_text"]


def test_opinions_surfaced_in_personality_context(tmp_path) -> None:
    p = _make_personality(tmp_path)
    ctx = p.get_personality_context()
    assert "On" in ctx  # opinionated stances are surfaced
    # technology is the highest-confidence opinion topic, so it must appear.
    assert "technology" in ctx


async def test_planner_uses_real_opinion_to_disagree(tmp_path) -> None:
    p = _make_personality(tmp_path)
    stage = ResponsePlannerStage(personality=p)

    class _Ctx:
        username: str = "tester"
        raw_content: str = "i hate technology, it's awful"
        intent: str = "social"
        beliefs: list[dict] = []
        response_plan: dict = {}

    # Run many times: a confident love vs stated hate must yield a disagree stance
    # at least once (stochastic, but confidence ~0.9 => ~80% of draws).
    saw_disagree = False
    for _ in range(50):
        ctx = _Ctx()
        await stage._run(ctx)  # type: ignore[attr-defined]
        plan = ctx.response_plan
        if plan.get("stance") in ("disagree_gently", "disagree_firmly"):
            saw_disagree = True
            break
    assert saw_disagree


async def test_planner_agrees_when_stance_aligned(tmp_path) -> None:
    p = _make_personality(tmp_path)
    stage = ResponsePlannerStage(personality=p)

    class _Ctx:
        username: str = "tester"
        raw_content: str = "i love technology too"
        intent: str = "social"
        beliefs: list[dict] = []
        response_plan: dict = {}

    saw_agree = False
    for _ in range(20):
        ctx = _Ctx()
        await stage._run(ctx)  # type: ignore[attr-defined]
        if ctx.response_plan.get("stance") == "agree":
            saw_agree = True
            break
    assert saw_agree
