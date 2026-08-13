"""Fixtures + helpers for the standing pipeline contract tests.

This suite reuses ``tools/pipeline_inspector`` as its offline harness: the REAL
``MessagePipeline`` is assembled with injected fakes (no Discord / Qdrant /
llamaswap required). On top of that we add contract-specific helpers:

- ``ContractFakeMemory`` — records ``store_recent_message`` calls so the
  bot-history write-gap (Cause 1) is assertable.
- ``ContractResult`` — wraps the post-run context + inspector and exposes
  stage-index lookups and the structured checkpoints the contract asserts on.
- ``run_contract`` — builds the pipeline for a scenario, gives the synthetic
  message a ``guild.me`` (so ``bot_id`` is computed exactly like production),
  and runs to completion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from tools.pipeline_inspector.checks import MODEL_PAYLOAD_KEY
from tools.pipeline_inspector.fakes import FakeMemorySystem, build_pipeline
from tools.pipeline_inspector.inspector import PipelineInspector
from tools.pipeline_inspector.scenario import Scenario

# The Discord id the synthetic message's guild.me resolves to. Matches the id
# MemoryWriteStage would attribute bot replies to in production.
BOT_USER_ID = "99999"


class ContractFakeMemory(FakeMemorySystem):
    """FakeMemorySystem that also records ``store_recent_message`` calls."""

    def __init__(self) -> None:
        super().__init__()
        self.recent_writes: list[dict[str, Any]] = []

    def store_recent_message(
        self,
        user_id: str,
        username: str,
        channel_id: str,
        content: str,
        message_id: str,
        timestamp: Any = None,
    ) -> None:
        self.recent_writes.append({
            "user_id": user_id,
            "username": username,
            "channel_id": channel_id,
            "content": content,
            "message_id": message_id,
        })


@dataclass
class ContractResult:
    """Post-run bundle: the final context plus the driving inspector."""

    ctx: MessageContext
    inspector: PipelineInspector
    memory: ContractFakeMemory = field(init=False)

    def __post_init__(self) -> None:
        mem_stage = next(
            s for s in self.inspector.stages
            if s.__class__.__name__ == "MemoryWriteStage"
        )
        self.memory = mem_stage.memory  # type: ignore[assignment]

    def stage_index(self, name: str) -> int:
        for i, s in enumerate(self.inspector.stages):
            if s.__class__.__name__ == name:
                return i
        raise KeyError(f"no stage named {name!r}")

    def state_after(self, name: str) -> dict[str, Any]:
        """Deep-copied ctx snapshot taken right after ``name`` ran."""
        return self.inspector.state_after(self.stage_index(name))

    @property
    def built_messages(self) -> list[dict[str, Any]]:
        """The full messages array handed to the model (system + context + history)."""
        return self.ctx.built_messages

    @property
    def model_payload(self) -> str | None:
        """The system-prompt content the LLM stage actually forwarded (Fix 3 point)."""
        return (self.ctx.metadata or {}).get(MODEL_PAYLOAD_KEY)


@pytest.fixture
def run_contract():
    """Build the real pipeline offline for a scenario and run it to completion.

    Usage::

        result = await run_contract(scenario, force_reply=False, dynamics_engine=...)
    """

    async def _run(
        scenario: Scenario,
        *,
        bot_id: str = BOT_USER_ID,
        force_reply: bool = True,
        response: str = "lol yeah that tracks honestly",
        **overrides: Any,
    ) -> ContractResult:
        memory = ContractFakeMemory()
        overrides.setdefault("memory_system", memory)
        pipeline = build_pipeline(
            scenario=scenario,
            response=response,
            force_reply=force_reply,
            **overrides,
        )
        inspector = PipelineInspector(pipeline)
        ctx = scenario.build_context()
        # Give the synthetic message a guild.me so bot_id is computed exactly
        # like production (needed for the bot-history assistant-role mapping).
        ctx.message.guild = SimpleNamespace(me=SimpleNamespace(id=int(bot_id)))
        ctx = await inspector.run_until(ctx)
        return ContractResult(ctx=ctx, inspector=inspector)

    return _run
