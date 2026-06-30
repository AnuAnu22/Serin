"""
serin.messaging.stages
---------------------
Each stage in the message pipeline. Stages are:
- Stateless with respect to MessageContext (they read + write ctx, nothing else)
- Independently instantiable
- Independently testable

Stages signal early exit by setting ctx.should_halt = True.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from serin.messaging.context import MessageContext
    from serin.messaging.context import PipelineDeps


class PipelineStage(ABC):
    """Base class for all message pipeline stages."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    async def run(self, ctx: "MessageContext", deps: "PipelineDeps") -> None:
        start = time.perf_counter()
        await self._run(ctx, deps)
        ctx.stage_timings[self.name] = round((time.perf_counter() - start) * 1000, 2)

    @abstractmethod
    async def _run(self, ctx: "MessageContext", deps: "PipelineDeps") -> None:
        ...


# Re-export all stage classes for easy access
from serin.messaging.stages.preparation import MessagePreparationStage  # noqa: E402
from serin.messaging.stages.memory_retrieval import MemoryRetrievalStage  # noqa: E402
from serin.messaging.stages.conversation import ConversationUpdateStage  # noqa: E402
from serin.messaging.stages.decision import ResponseDecisionStage  # noqa: E402
from serin.messaging.stages.context_assembly import ContextAssemblyStage  # noqa: E402
from serin.messaging.stages.active_search import ActiveSearchStage  # noqa: E402
from serin.messaging.stages.voice_action import VoiceActionStage  # noqa: E402
from serin.messaging.stages.generation import GenerationStage  # noqa: E402

__all__ = [
    "PipelineStage",
    "MessagePreparationStage",
    "MemoryRetrievalStage",
    "ConversationUpdateStage",
    "ResponseDecisionStage",
    "ContextAssemblyStage",
    "ActiveSearchStage",
    "VoiceActionStage",
    "GenerationStage",
]
