"""Contract: system prompt + relationship bias assembled correctly.

These tests force a reply (creator override) so the pipeline deterministically
reaches PromptAssemblyStage + LLMCallStage; the halt path is covered
separately in ``test_decision_halt.py``.

Scenario A — Fresh stranger (familiarity < 0.1): the system prompt must carry
the Serin persona and NO per-relationship bias section, because
``_affect_context`` returns "" for near-strangers.

Scenario B — Established friend (familiarity >= 0.5, valence > 0.3): the
relationship bias ("Your feelings about <user>") must appear in the assembled
messages that reach the model (``built_messages`` — the exact
``current_messages`` argument handed to ``chat_completion``).
"""
from __future__ import annotations

from tools.pipeline_inspector.scenario import Scenario, _Snap


def _joined_built(ctx) -> str:
    return "\n".join(m["content"] for m in ctx.built_messages)


async def test_stranger_system_prompt_has_persona_no_relationship_bias(
    run_contract,
) -> None:
    scenario = Scenario(
        content="hey who are you",
        user_id="1234",
        username="Newbie",
        affect=_Snap(valence=0.0, familiarity=0.0),  # stranger
    )
    result = await run_contract(scenario)  # default: force_reply=True

    # Checkpoint: pipeline must reach the LLM stage (prompt assembled).
    assert result.ctx.halt_reason == "", (
        f"stranger message unexpectedly halted: {result.ctx.halt_reason!r}"
    )

    built = result.built_messages
    assert built, "built_messages is empty — prompt never assembled"
    system = next((m["content"] for m in built if m["role"] == "system"), "")
    assert "You are Serin" in system, (
        "system prompt missing Serin persona at PromptAssemblyStage"
    )

    # The feelings/bias section must be absent for a stranger.
    joined = _joined_built(result.ctx)
    assert "Your feelings about Newbie" not in joined, (
        "relationship bias section leaked into a STRANGER's prompt — "
        "familiarity<0.1 should suppress it"
    )


async def test_friend_relationship_bias_reaches_model(run_contract) -> None:
    scenario = Scenario(
        content="hey serin remember that time we went to the lake",
        user_id="137",
        username="Rin",
        affect=_Snap(valence=0.8, familiarity=0.9),  # established friend
        recent_messages=[
            {"user_id": "137", "username": "Rin", "content": "we should do that again"},
        ],
    )
    result = await run_contract(scenario)  # default: force_reply=True

    assert result.ctx.halt_reason == "", (
        f"friend message unexpectedly halted: {result.ctx.halt_reason!r}"
    )

    joined = _joined_built(result.ctx)

    # Checkpoint: bias section present in the messages that reach the model.
    # built_messages IS the current_messages payload passed to chat_completion
    # (PromptAssemblyStage emits [system_prompt, context_block, *history]).
    assert "Your feelings about Rin" in joined, (
        "relationship bias section missing from the messages that reach the "
        f"model for a FRIEND (familiarity=0.9, valence=0.8). Got:\n{joined[:500]}"
    )
