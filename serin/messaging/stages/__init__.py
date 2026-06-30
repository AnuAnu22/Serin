"""
serin.messaging.stages
---------------------
Each stage in the message pipeline. Stages are:
- Stateless with respect to MessageContext (they read + write ctx, nothing else)
- Independently instantiable
- Independently testable

Stages signal early exit by setting ctx.halt_reason to a non-empty string.
They do NOT raise exceptions for expected early exits (e.g. "should not respond").
They DO raise exceptions for unexpected failures (handled by the pipeline runner).
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from serin.messaging.context import MessageContext


class PipelineStage(ABC):
    """Base class for all message pipeline stages."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    async def run(self, ctx: MessageContext) -> MessageContext:
        start = time.perf_counter()
        ctx = await self._run(ctx)
        ctx.stage_timings[self.name] = round((time.perf_counter() - start) * 1000, 2)
        return ctx

    @abstractmethod
    async def _run(self, ctx: MessageContext) -> MessageContext:
        """Implement the stage logic here."""
        ...


# Re-export all stage classes for easy access
from serin.messaging.stages.decision import ResponseDecisionStage  # noqa: E402
from serin.messaging.stages.memory_retrieval import MemoryRetrievalStage  # noqa: E402
from serin.messaging.stages.temporal import TemporalStage  # noqa: E402
from serin.messaging.stages.personality import PersonalityStage  # noqa: E402
from serin.messaging.stages.prompt_assembly import PromptAssemblyStage  # noqa: E402
from serin.messaging.stages.llm_call import LLMCallStage  # noqa: E402
from serin.messaging.stages.response_cleaning import ResponseCleaningStage  # noqa: E402
from serin.messaging.stages.send import SendStage  # noqa: E402
from serin.messaging.stages.memory_write import MemoryWriteStage  # noqa: E402

__all__ = [
    "PipelineStage",
    "ResponseDecisionStage",
    "MemoryRetrievalStage",
    "TemporalStage",
    "PersonalityStage",
    "PromptAssemblyStage",
    "LLMCallStage",
    "ResponseCleaningStage",
    "SendStage",
    "MemoryWriteStage",
]
