"""Contract: decision-stage halt runs tail + no downstream prompt assembly.

A message the Boltzmann engine decides to IGNORE (no creator / mention /
bot-name override) must:
  - halt the pipeline with ``halt_reason == "boltzmann_ignore"``;
  - STILL run MemoryWriteStage as the tail (facts must be extracted even when
    the bot doesn't reply);
  - NOT assemble any prompt / capture any model payload downstream of the halt
    (no LLM call happened).
"""
from __future__ import annotations

from serin.d1_3_state_core.d2_5_state_conversation.d3_1_dynamics_engine import (
    ConversationDynamicsEngine,
)
from tools.pipeline_inspector.scenario import Scenario, _Snap


class _IgnoreDynamics(ConversationDynamicsEngine):
    """Dynamics engine that always tells the bot to ignore non-override input."""

    def decide_action(self, *args: object, **kwargs: object) -> str:
        return "ignore"


async def test_boltzmann_ignore_halts_and_runs_memory_write_tail(
    run_contract,
) -> None:
    # No override: not creator, no @mention, no "serin" in content.
    scenario = Scenario(
        content="the weather is fine i guess",
        user_id="777",
        username="Moss",
        affect=_Snap(valence=0.0, familiarity=0.0),
    )
    result = await run_contract(
        scenario,
        force_reply=False,
        dynamics_engine=_IgnoreDynamics(),
    )

    # Checkpoint 1: the decision stage halted the flow.
    assert result.ctx.halt_reason == "boltzmann_ignore", (
        f"expected boltzmann_ignore halt, got {result.ctx.halt_reason!r}"
    )
    assert result.ctx.should_respond is False, "bot should not respond when ignored"

    # Checkpoint 2: MemoryWriteStage (the tail) still ran despite the halt.
    assert "MemoryWriteStage" in result.ctx.stage_timings, (
        "MemoryWriteStage tail did NOT run after a halt — facts would be lost"
    )

    # Checkpoint 3: no LLM call happened downstream of the halt, so no model
    # payload was captured and no built_messages were assembled for dispatch.
    assert result.model_payload is None, (
        "an LLM payload was captured despite the pipeline halting before the "
        "LLM stage — prompt assembly must not happen downstream of a halt"
    )
    assert not result.built_messages or all(
        m["role"] != "assistant" for m in result.built_messages
    ), "assistant content assembled even though the bot never reached the LLM stage"
