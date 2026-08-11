"""Fake discord.Message for offline pipeline inspection.

The real stages touch only a handful of attrs on `ctx.message`: ``id``,
``author``, ``channel``, ``guild``, ``mentions``, ``add_reaction``. This
shim provides those as plain data so the full pipeline runs with no live
Discord connection. ``guild=None`` deliberately short-circuits the mention
hard-override check (``if message.guild and message.guild.me``) in
`ResponseDecisionStage` and the bot_id lookup in `PromptAssemblyStage`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class _Author:
    id: int
    display_name: str = "Sam"


@dataclass
class _Channel:
    id: int

    async def send(self, content: str) -> None:
        return None

    def typing(self):  # async context manager no-op
        class _Ctx:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, *a: Any) -> None:
                return None

        return _Ctx()


@dataclass
class FakeMessage:
    """Minimal stand-in for :class:`discord.Message`."""

    content: str
    author_id: int = 5
    author_name: str = "Sam"
    channel_id: int = 999
    guild: Any = None
    mentions: list[Any] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def id(self) -> int:
        return abs(hash((self.author_id, self.channel_id, self.content)))

    @property
    def author(self) -> _Author:
        return _Author(self.author_id, self.author_name)

    @property
    def channel(self) -> _Channel:
        return _Channel(self.channel_id)

    async def add_reaction(self, emoji: str) -> None:
        return None


__all__ = ["FakeMessage"]
