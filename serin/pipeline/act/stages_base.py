"""PipelineStage base class."""
from __future__ import annotations
import time
from abc import ABC, abstractmethod
from serin.state.message_context import MessageContext


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


__all__ = ["PipelineStage"]
