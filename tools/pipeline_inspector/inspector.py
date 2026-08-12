"""PipelineInspector — drive the REAL MessagePipeline with breakpoints.

The driver's ``run_until`` replicates ``MessagePipeline.process()``'s control
flow EXACTLY (see ``serin/.../d4_2_runners_pipeline.py:106-163``):

- per-stage try/except, on exception ``ctx.halt_reason = f"stage_error:{name}"``
  and the loop breaks;
- after each stage, if ``ctx.halt_reason`` is set, the loop breaks;
- the tail then runs ``MemoryWriteStage`` even when the pipeline halted
  (facts must still be extracted).

Unlike ``process()``, the inspector records a deep-copied snapshot of
``MessageContext`` at every stage boundary so downstream tooling (diff, dump)
can compare the state between stage N and N+1 without the in-place mutations
of the live ctx having overwritten it.
"""
from __future__ import annotations

import dataclasses
from copy import deepcopy
from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
    MessagePipeline,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from tools.pipeline_inspector.checks import MODEL_PAYLOAD_KEY
from tools.pipeline_inspector.fakes import build_pipeline
from tools.pipeline_inspector.scenario import Scenario


def snapshot_ctx(ctx: MessageContext) -> dict[str, Any]:
    """Deep-copy MessageContext into a plain dict for diffing.

    The only non-serializable field is ``message`` (a live discord.Message);
    it is summarized to its identity fields.
    """
    snap: dict[str, Any] = {}
    for f in dataclasses.fields(MessageContext):
        name = f.name
        val = getattr(ctx, name)
        if name == "message":
            msg: Any = val
            author = getattr(msg, "author", None)
            snap["message"] = {
                "id": getattr(msg, "id", None),
                "author_id": getattr(author, "id", None),
                "content_preview": (getattr(msg, "content", "") or "")[:60],
                "guild_id": getattr(msg, "guild", None),
            }
            continue
        try:
            snap[name] = deepcopy(val)
        except Exception:  # pragma: no cover - defensive fallback
            snap[name] = repr(val)
    return snap


class PipelineInspector:
    """Drives a MessagePipeline stage-by-stage, recording boundary snapshots."""

    def __init__(self, pipeline: MessagePipeline) -> None:
        self.pipeline = pipeline
        self.stages = pipeline.stages
        self._pos = 0
        self.events: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []

    @classmethod
    def from_scenario(
        cls,
        scenario: Scenario,
        *,
        force_reply: bool = True,
        response: str = "lol yeah that tracks honestly",
        **overrides: Any,
    ) -> PipelineInspector:
        """Build an inspector from a Scenario, forcing a reply by default so the
        full flow is observable (creator hard-override in the real decision stage)."""
        pipeline = build_pipeline(
            scenario=scenario,
            response=response,
            force_reply=force_reply,
            **overrides,
        )
        return cls(pipeline)

    def reset(self) -> None:
        self._pos = 0
        self.events = []
        self.snapshots = []

    def state_after(self, index: int) -> dict[str, Any]:
        """Snapshot of ctx after stage ``index`` ran (indexes into self.snapshots)."""
        return self.snapshots[index + 1]

    async def run_until(
        self,
        ctx: MessageContext,
        stop_after: int | None = None,
    ) -> MessageContext:
        """Run stages from the current position through ``stop_after`` (inclusive).

        ``stop_after=None`` runs to completion (or halt). Repeats calls resume
        from the saved position, enabling step/mutate/continue.
        """
        if not self.snapshots:
            self.snapshots.append(snapshot_ctx(ctx))

        memory_write = self.stages[-1]
        is_memory_write_tail = memory_write.__class__.__name__ == "MemoryWriteStage"

        for stage_index in range(self._pos, len(self.stages)):
            if stop_after is not None and stage_index > stop_after:
                break
            stage = self.stages[stage_index]
            try:
                ctx = await stage.run(ctx)
            except Exception as exc:
                ctx.halt_reason = f"stage_error:{stage.name}"
                self.events.append({
                    "index": stage_index,
                    "stage": stage.name,
                    "status": "error",
                    "error": str(exc),
                })
                self.snapshots.append(snapshot_ctx(ctx))
                self._pos = stage_index + 1
                break
            self._capture_model_payload(ctx, stage)
            self.events.append({
                "index": stage_index,
                "stage": stage.name,
                "status": "skipped" if ctx.halt_reason else "done",
            })
            self.snapshots.append(snapshot_ctx(ctx))
            self._pos = stage_index + 1
            if ctx.halt_reason:
                break

        # Tail — MemoryWriteStage always runs even if the pipeline halted
        # (mirrors process() lines 148-154).
        loop_finished = self._pos >= len(self.stages)
        if (loop_finished or ctx.halt_reason) and is_memory_write_tail and ctx.halt_reason:
            try:
                ctx = await memory_write.run(ctx)
            except Exception as exc:
                self.events.append({
                    "index": len(self.stages) - 1,
                    "stage": memory_write.name,
                    "status": "tail_error",
                    "error": str(exc),
                })
            else:
                self.events.append({
                    "index": len(self.stages) - 1,
                    "stage": memory_write.name,
                    "status": "tail",
                })
            self.snapshots.append(snapshot_ctx(ctx))
        return ctx

    def _capture_model_payload(self, ctx: MessageContext, stage: Any) -> None:
        """Record what the LLM stage actually forwarded to the model.

        The inspector's fake generator keeps ``last_payload_system`` - the
        system prompt it would send (via the same ``resolve_system_prompt`` the
        real ``get_response_natural`` uses). We copy it into ``ctx.metadata``
        so ``planner_constraints_survive`` asserts against the real payload,
        not an intermediate field a downstream rebuild may discard.
        """
        if stage.__class__.__name__ != "LLMCallStage":
            return
        recorded = getattr(getattr(stage, "generator", None), "last_payload_system", None)
        if recorded:
            ctx.metadata[MODEL_PAYLOAD_KEY] = recorded


__all__ = ["PipelineInspector", "snapshot_ctx"]
