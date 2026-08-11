"""Synthetic-scenario builder for the pipeline inspector.

A :class:`Scenario` is the one-line way to set up a message-pipeline run:
plain user_id/content/channel plus optional pre-seeded affect, facts,
beliefs, recent messages, and user profile. :meth:`Scenario.build_context`
returns a real :class:`MessageContext` (with a :class:`FakeMessage`
standing in for the live Discord message) matching how
`EnhancedMessageManagerV3` constructs one in production.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from tools.pipeline_inspector.fake_message import FakeMessage


@dataclass
class _Snap:
    """A canned affect snapshot (asseen of the user at pipeline entry)."""

    valence: float
    familiarity: float
    impression: str = ""


@dataclass
class Scenario:
    content: str
    user_id: str = "1234"
    username: str = "Sam"
    channel_id: str = "inspector"
    guild_id: str | None = None
    is_mentioned: bool = False
    affect: _Snap | None = None
    facts: list[dict[str, Any]] = field(default_factory=list)
    beliefs: list[dict[str, Any]] = field(default_factory=list)
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    user_profile: dict[str, Any] = field(default_factory=dict)

    def build_context(self) -> MessageContext:
        channel_id = int(self.channel_id) if self.channel_id.isdigit() else 999
        msg = FakeMessage(self.content, channel_id=channel_id)
        return MessageContext(
            message=msg,
            user_id=self.user_id,
            username=self.username,
            channel_id=self.channel_id,
            guild_id=self.guild_id,
            raw_content=self.content,
            is_mentioned=self.is_mentioned,
        )


__all__ = ["Scenario", "_Snap"]
