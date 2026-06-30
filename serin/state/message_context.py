"""
serin.messaging.context
----------------------
MessageContext is the data envelope that flows through the message pipeline.
Every stage reads from it and writes to it. No stage has side effects
outside of what it writes into the context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import discord


@dataclass
class MessageContext:
    # ── Input (set at pipeline entry, never mutated) ──────────────────────────
    message: discord.Message
    user_id: str
    username: str
    channel_id: str
    guild_id: str | None
    raw_content: str

    # ── Decision ──────────────────────────────────────────────────────────────
    should_respond: bool = False
    halt_reason: str = ""  # non-empty = pipeline halted early
    intent: str = "statement"  # from PerceptionResult
    response_plan: dict = field(default_factory=dict)  # from ResponsePlannerStage

    # ── Memory retrieval ──────────────────────────────────────────────────────
    memories: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)  # From FactStore
    beliefs: list[dict] = field(default_factory=list)  # From BeliefStore
    evidence_memories: list[dict] = field(default_factory=list)
    episode_memories: list[dict] = field(default_factory=list)
    utterance_memories: list[dict] = field(default_factory=list)
    recent_messages: list[dict] = field(default_factory=list)
    user_profile: dict = field(default_factory=dict)
    relationships: list[dict] = field(default_factory=list)

    # ── Temporal / context ────────────────────────────────────────────────────
    temporal_refs: list[str] = field(default_factory=list)
    personality_context: str = ""
    tone_modifier: str = ""

    # ── Prompt assembly ───────────────────────────────────────────────────────
    system_prompt: str = ""
    context_block: str = ""
    built_messages: list[dict] = field(default_factory=list)  # [{role, content}]

    # ── LLM response ──────────────────────────────────────────────────────────
    raw_response: str = ""
    final_response: str = ""

    # ── Observability ─────────────────────────────────────────────────────────
    stage_timings: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)  # catch-all for stage extras
