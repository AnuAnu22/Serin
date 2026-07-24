"""
ResponseDecisionStage
---------------------
Decides whether Serin should respond to this message at all.
Sets ctx.should_respond. If False, sets ctx.halt_reason and pipeline halts.
"""
from __future__ import annotations

import secrets
import time
from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_3_state_core.d2_5_message_context import MessageContext
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_5_server_websocket import (
    broadcast_event,
)

# Track messages Serin "missed" to bring up later
_missed_messages: dict[str, list[dict[str, Any]]] = {}


def _human_miss_check(ctx: MessageContext, is_addressed: bool) -> bool:
    """Sometimes Serin misses a message, like a human would.

    - If directly addressed (@mention or name): 5% miss chance
    - Missed messages are stored to reference later.
    """
    if not is_addressed:
        return False

    channel_id = str(ctx.channel_id)
    user_id = str(ctx.user_id)
    username = str(ctx.username)
    content = str(ctx.raw_content)

    miss_chance = 5  # 5% chance
    if secrets.randbelow(100) < miss_chance:
        if channel_id not in _missed_messages:
            _missed_messages[channel_id] = []
        _missed_messages[channel_id].append({
            "user_id": user_id,
            "username": username,
            "content": content[:200],
            "timestamp": time.time(),
        })
        _missed_messages[channel_id] = _missed_messages[channel_id][-10:]
        logger.debug("Serin missed a message from %s in %s (human-like)", username, channel_id)
        return True

    return False


async def _maybe_add_reaction(ctx: MessageContext) -> bool:
    """Serin might add a Discord reaction to express a feeling about a message.

    Uses Discord's add_reaction() — the emoji stays ON the message.
    This is NOT random. It happens when the bot feels strongly about
    something and wants to express it in one character.

    The bot may or may not follow up with a text response.
    """
    content = getattr(ctx, 'raw_content', '')
    message = getattr(ctx, 'message', None)
    if not message:
        return False

    content_lower = content.lower()

    # Analyze what the bot feels about this message
    emoji: str | None = None

    # Funny / hilarious — bot finds it amusing
    if any(w in content_lower for w in ['lol', 'lmao', 'haha', 'funny', 'joke', 'dead', '💀']):
        emoji = secrets.choice(['😂', '💀', '😭'])

    # Impressive / cool — bot is impressed
    elif any(w in content_lower for w in ['wow', 'cool', 'nice', 'sick', 'awesome', 'epic', 'insane', 'goated']):
        emoji = secrets.choice(['🔥', '👀', '💯'])

    # Sad / unfortunate — bot feels bad
    elif any(w in content_lower for w in ['sad', 'rip', 'unfortunately', 'lost', 'fail', 'oof', 'pain', 'suffering']):
        emoji = secrets.choice(['😢', '💔', '😔'])

    # Victory / hype — bot is excited
    elif any(w in content_lower for w in ['won', 'win', 'gg', 'letsgo', 'hype', 'champion', 'first']):
        emoji = secrets.choice(['🎉', '🔥', '👏'])

    # Agreement — bot agrees strongly
    elif any(w in content_lower for w in ['agree', 'true', 'facts', 'real', 'fr', 'exactly', 'this']):
        emoji = secrets.choice(['👍', '💯', '✅'])

    # Love / wholesome — bot feels warm
    elif any(w in content_lower for w in ['love', 'cute', 'wholesome', 'adorable', 'sweet', '❤️']):
        emoji = secrets.choice(['❤️', '🥰', '💜'])

    # If no strong feeling detected, don't react
    if emoji is None:
        return False

    try:
        await message.add_reaction(emoji)
        logger.info("Serin reacted with %s to message from %s: '%s'",
                     emoji, ctx.username, content[:50])
        return True
    except Exception as e:
        logger.debug("Failed to add reaction: %s", e)
        return False


def get_missed_messages(channel_id: str) -> list[dict[str, Any]]:
    """Get messages Serin 'missed' in this channel."""
    msgs = _missed_messages.get(str(channel_id), [])
    cutoff = time.time() - 7200
    recent = [m for m in msgs if m["timestamp"] > cutoff]
    _missed_messages[str(channel_id)] = recent
    return recent


def clear_missed_messages(channel_id: str) -> None:
    """Clear missed messages for a channel after referencing them."""
    _missed_messages[str(channel_id)] = []


async def _broadcast_decision(ctx: MessageContext, decision: str, reason: str) -> None:
    """Publish a decision event without interrupting message handling."""
    try:
        channel = getattr(getattr(ctx, "message", None), "channel", None)
        await broadcast_event("decision", {
            "user": str(getattr(ctx, "username", "")),
            "channel": str(getattr(channel, "name", "")),
            "channel_id": str(getattr(ctx, "channel_id", "")),
            "decision": decision,
            "reason": reason,
            "content_preview": str(getattr(ctx, "raw_content", ""))[:80],
        })
    except Exception as exc:
        logger.debug("Failed to broadcast decision: %s", exc)


class ResponseDecisionStage(PipelineStage):
    """Decides whether to respond based on mention, rate limits, and DM rules."""

    def __init__(self, response_controller: Any) -> None:
        self.controller = response_controller

    async def _run(self, ctx: MessageContext) -> MessageContext:
        should_respond, reason = self.controller.should_respond(
            message_content=ctx.raw_content,
            channel_id=ctx.channel_id,
            bot_mentioned=ctx.message.guild is not None
            and ctx.message.guild.me in ctx.message.mentions,
            user_id=ctx.user_id,
            recent_messages=[],
        )

        if not should_respond:
            ctx.should_respond = False
            ctx.halt_reason = reason or "no_response_needed"
            await _broadcast_decision(ctx, "SKIP", ctx.halt_reason)
            logger.debug("pipeline.decision", extra={
                "user": ctx.username,
                "user_id": ctx.user_id,
                "channel_id": ctx.channel_id,
                "decision": False,
                "reason": ctx.halt_reason,
            })
            return ctx

        # Human-like: sometimes miss even when addressed
        if _human_miss_check(ctx, is_addressed=True):
            ctx.should_respond = False
            ctx.halt_reason = "human_miss"
            await _broadcast_decision(ctx, "MISS", "human-like miss (5% chance)")
            logger.debug("pipeline.decision", extra={
                "user": ctx.username,
                "user_id": ctx.user_id,
                "channel_id": ctx.channel_id,
                "decision": False,
                "reason": "human_miss",
            })
            return ctx

        # Sometimes add a reaction to express a feeling (bot may still respond with text)
        try:
            reacted = await _maybe_add_reaction(ctx)
            if reacted:
                await _broadcast_decision(ctx, "REACT", "emoji reaction")
        except Exception as exc:
            logger.debug("Reaction attempt failed: %s", exc)

        ctx.should_respond = True
        await _broadcast_decision(ctx, "RESPOND", "relevant to conversation")
        logger.debug("pipeline.decision", extra={
            "user": ctx.username,
            "user_id": ctx.user_id,
            "channel_id": ctx.channel_id,
            "decision": True,
            "reason": "will_respond",
        })
        return ctx


class TemporalStage(PipelineStage):
    """Parses and resolves temporal references in user input."""

    def __init__(self, temporal_context: Any) -> None:
        self.temporal = temporal_context

    async def _run(self, ctx: MessageContext) -> MessageContext:
        if not hasattr(self.temporal, "resolve_dates"):
            return ctx

        resolved = self.temporal.resolve_dates(ctx.raw_content)
        if resolved:
            ctx.temporal_refs = resolved
            logger.debug("pipeline.temporal_resolved", extra={
                "user": ctx.username,
                "refs_found": len(resolved),
                "refs": resolved,
            })
        else:
            ctx.temporal_refs = []

        return ctx
