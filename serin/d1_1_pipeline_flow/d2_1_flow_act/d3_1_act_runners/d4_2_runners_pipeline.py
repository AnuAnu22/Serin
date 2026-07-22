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

from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_3_state_core.d2_5_message_context import MessageContext


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
        from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_3_prompt_assembly import (
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

        return cls(stages=[
            ResponseDecisionStage(response_controller),
            MemoryRetrievalStage(memory_system, retrieval),
            ResponsePlannerStage(),
            TemporalStage(temporal_context),
            PersonalityStage(personality, mood_state=mood_state),
            PromptAssemblyStage(mention_translator),
            LLMCallStage(response_generator),
            ResponseCleaningStage(thinking_filter),
            SendStage(),
            MemoryWriteStage(memory_system),
        ])

    async def process(self, ctx: MessageContext) -> MessageContext:
        logger.info("pipeline.start", extra={
            "user": ctx.username,
            "user_id": ctx.user_id,
            "channel_id": ctx.channel_id,
            "content_preview": ctx.raw_content[:60],
        })

        for stage in self.stages:
            try:
                ctx = await stage.run(ctx)
            except Exception as e:
                logger.error("pipeline.stage_error", extra={
                    "stage": stage.name,
                    "user": ctx.username,
                    "error": str(e),
                }, exc_info=True)
                ctx.halt_reason = f"stage_error:{stage.name}"
                break

            if ctx.halt_reason:
                logger.debug("pipeline.halted", extra={
                    "stage": stage.name,
                    "reason": ctx.halt_reason,
                })
                break

        logger.info("pipeline.complete", extra={
            "user": ctx.username,
            "responded": bool(ctx.final_response),
            "halt_reason": ctx.halt_reason or None,
            "total_ms": round(sum(ctx.stage_timings.values()), 2),
            "stage_timings": ctx.stage_timings,
        })
        return ctx


