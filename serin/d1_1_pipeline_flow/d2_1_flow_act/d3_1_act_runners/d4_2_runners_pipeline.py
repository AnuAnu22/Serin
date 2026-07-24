"""
serin.messaging.pipeline
-----------------------
MessagePipeline is the entry point for all text message processing.
It runs stages in order, passing MessageContext through each.

Stages signal early exit via ctx.halt_reason (non-empty string).
Unexpected exceptions are caught, logged, and halt the pipeline.

Usage:
    pipeline = MessagePipeline.build(memory_system, model, personality, ...)
    ctx = MessageContext(message=msg, ...)
    ctx = await pipeline.process(ctx)
"""
from __future__ import annotations

import time
from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_3_state_core.d2_5_state_conversation.d3_1_dynamics_engine import (
    ConversationDynamicsEngine,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_4_config_base.d2_3_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_8_server.d5_2_server_websocket import (
    broadcast_event,
)


class MessagePipeline:
    def __init__(self, stages: list[PipelineStage]) -> None:
        self.stages = stages

    @classmethod
    def build(
        cls,
        *,
        response_controller: Any,
        memory_system: Any,
        retrieval: Any,
        personality: Any,
        temporal_context: Any,
        response_generator: Any,
        thinking_filter: Any,
        mention_translator: Any,
        mood_state: Any = None,
        client: Any = None,
        small_llm: Any = None,
        dynamics_engine: Any | None = None,
    ) -> MessagePipeline:
        """
        Factory method — wires all dependencies into stages.
        Call this once at bot startup. Keep the instance for the bot's lifetime.
        """
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_1_runners_dispatch.d5_1_llm_call import (
            LLMCallStage,
        )
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_1_runners_dispatch.d5_2_dispatch_send import (
            SendStage,
        )
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_3_prompt_assembly.d5_1_prompt_assembly import (
            PromptAssemblyStage,
        )
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_4_response_cleaning import (
            ResponseCleaningStage,
        )
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_1_decision_temporal import (
            ResponseDecisionStage,
            TemporalStage,
        )
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_2_memory_retrieval import (
            MemoryRetrievalStage,
        )
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_3_memory_write import (
            MemoryWriteStage,
        )
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_4_personality_stage import (
            PersonalityStage,
        )
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_4_response_planner import (
            ResponsePlannerStage,
        )

        dynamics = dynamics_engine or ConversationDynamicsEngine()

        return cls(stages=[
            ResponseDecisionStage(response_controller, dynamics=dynamics),
            MemoryRetrievalStage(memory_system, retrieval),
            ResponsePlannerStage(),
            TemporalStage(temporal_context),
            PersonalityStage(personality, mood_state=mood_state),
            PromptAssemblyStage(mention_translator, memory_system=memory_system),
            LLMCallStage(response_generator),
            ResponseCleaningStage(thinking_filter),
            SendStage(dynamics=dynamics),
            MemoryWriteStage(memory_system, personality=mood_state, client=client, small_llm=small_llm),
        ])

    async def process(self, ctx: MessageContext) -> MessageContext:
        logger.info("pipeline.start", extra={
            "user": ctx.username,
            "user_id": ctx.user_id,
            "channel_id": ctx.channel_id,
            "content_preview": ctx.raw_content[:60],
        })

        for stage_index, stage in enumerate(self.stages):
            stage_start = time.perf_counter()
            event_base = {
                "stage_id": stage_index,
                "stage_name": stage.__class__.__name__,
                "channel_id": str(getattr(ctx, "channel_id", "")),
                "user": getattr(ctx, "username", ""),
            }
            await broadcast_event("pipeline_stage", {**event_base, "status": "running"})
            try:
                ctx = await stage.run(ctx)
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - stage_start) * 1000, 1)
                await broadcast_event("pipeline_stage", {
                    **event_base, "status": "error", "elapsed_ms": elapsed_ms,
                })
                logger.error("pipeline.stage_error", extra={
                    "stage": stage.name, "user": ctx.username, "error": str(exc),
                }, exc_info=True)
                ctx.halt_reason = f"stage_error:{stage.name}"
                break
            elapsed_ms = round((time.perf_counter() - stage_start) * 1000, 1)
            await broadcast_event("pipeline_stage", {
                **event_base,
                "status": "skipped" if ctx.halt_reason else "done",
                "elapsed_ms": elapsed_ms,
            })
            if ctx.halt_reason:
                logger.debug("pipeline.halted", extra={
                    "stage": stage.name,
                    "reason": ctx.halt_reason,
                })
                break

        # Always run MemoryWriteStage even if pipeline halted (facts must be extracted)
        memory_write_stage = self.stages[-1]
        if memory_write_stage.__class__.__name__ == "MemoryWriteStage" and ctx.halt_reason:
            try:
                ctx = await memory_write_stage.run(ctx)
            except Exception as exc:
                logger.error("memory_write.error", extra={"error": str(exc)})

        logger.info("pipeline.complete", extra={
            "user": ctx.username,
            "responded": bool(ctx.final_response),
            "halt_reason": ctx.halt_reason or None,
            "total_ms": round(sum(ctx.stage_timings.values()), 2),
            "stage_timings": ctx.stage_timings,
        })
        return ctx


