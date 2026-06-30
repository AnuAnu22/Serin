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

from serin.state.message_context import MessageContext
from serin.pipeline.act.stages_init import PipelineStage
from serin.config.logger import logger


class MessagePipeline:
    def __init__(self, stages: list[PipelineStage]) -> None:
        self.stages = stages

    @classmethod
    def build(
        cls,
        *,
        response_controller,
        memory_system,
        retrieval,
        personality,
        temporal_context,
        response_generator,
        thinking_filter,
        mention_translator,
        mood_state=None,
    ) -> "MessagePipeline":
        """
        Factory method — wires all dependencies into stages.
        Call this once at bot startup. Keep the instance for the bot's lifetime.
        """
        from serin.pipeline.act.decision import ResponseDecisionStage
        from serin.pipeline.act.memory_retrieval import MemoryRetrievalStage
        from serin.pipeline.think.response_planner import ResponsePlannerStage
        from serin.pipeline.act.temporal import TemporalStage
        from serin.pipeline.act.personality_stage import PersonalityStage
        from serin.pipeline.act.prompt_assembly import PromptAssemblyStage
        from serin.pipeline.act.llm_call import LLMCallStage
        from serin.pipeline.act.response_cleaning import ResponseCleaningStage
        from serin.pipeline.act.send import SendStage
        from serin.pipeline.act.memory_write import MemoryWriteStage

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
