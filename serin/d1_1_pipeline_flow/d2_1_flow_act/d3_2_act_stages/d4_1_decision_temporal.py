"""
ResponseDecisionStage
---------------------
Decides whether Serin should respond to this message at all.
Uses the ConversationDynamicsEngine for continuous physics-based
decision making (Boltzmann action selection).

Rules 1-3 (creator, @mention, bot name) are hard overrides
that bypass the physics engine entirely.
"""
from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_4_config_base.d2_3_core_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_8_server.d5_2_server_websocket import (
    broadcast_event,
)

_missed_messages: dict[str, list[dict[str, Any]]] = {}


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


class ResponseDecisionStage(PipelineStage):
    """Decides whether to respond using Boltzmann physics engine."""

    def __init__(self, dynamics: Any | None = None,
                 creator_ids: frozenset[str] | None = None,
                 affect_engine: Any | None = None,
                 goals_engine: Any | None = None) -> None:
        self.dynamics = dynamics
        self.creator_ids: frozenset[str] = creator_ids or frozenset()
        self.affect_engine = affect_engine
        self.goals_engine = goals_engine

    def _goal_salience_bonus(self, goals: list[dict[str, Any]]) -> float:
        """Deterministic, bounded engagement lift from actively-pursued goals.

        Each goal contributes 0.10 x its salience; the sum is the lift applied
        to message salience before the Boltzmann decision. No randomness: the
        weight is read straight from accumulated goal state (causality, not
        performance). Statements are never read here - only their salience.
        """
        bonus = 0.0
        for goal in goals[:3]:
            try:
                bonus += 0.10 * float(goal.get("salience", 0.0))
            except (TypeError, ValueError):
                continue
        return bonus

    def _pick_reaction_emoji(self, content: str) -> str:
        """Pick an emoji reaction based on content."""
        content_lower = content.lower()
        if any(w in content_lower for w in ['lol', 'lmao', 'haha', 'funny', '😂']):
            return secrets.choice(['😂', '💀', '😭'])
        elif any(w in content_lower for w in ['wow', 'cool', 'nice', 'sick', 'awesome']):
            return secrets.choice(['🔥', '👀', '💯'])
        elif any(w in content_lower for w in ['sad', 'rip', 'oof', 'unfortunately']):
            return secrets.choice(['😢', '💔', '😔'])
        elif any(w in content_lower for w in ['gg', 'won', 'letsgo', 'hype']):
            return secrets.choice(['🎉', '🔥', '👏'])
        else:
            return secrets.choice(['👀', '👍', '😂', '💀', '❤️'])

    async def _run(self, ctx: MessageContext) -> MessageContext:
        # HARD OVERRIDES — bypass physics engine
        message = ctx.message
        is_mentioned = False
        if message.guild and message.guild.me:
            is_mentioned = message.guild.me in message.mentions

        is_creator = str(ctx.user_id) in self.creator_ids
        name_in_msg = 'serin' in ctx.raw_content.lower()

        hard_override = is_creator or is_mentioned or name_in_msg
        if is_creator:
            # The dev is testing live — reply immediately, no Hawkes delay.
            ctx.metadata["instant_reply"] = True

        # Update physics state
        if self.dynamics:
            self.dynamics.observe_message(
                channel_id=ctx.channel_id,
                content=ctx.raw_content,
                user_id=ctx.user_id,
                timestamp=time.time(),
            )
            self.dynamics.allocate_attention()

        # Calculate salience — familiarity raises base interest slightly
        snap = self.affect_engine.snapshot_cached(ctx.user_id) if self.affect_engine else None
        salience = 0.3
        if '?' in ctx.raw_content:
            salience += 0.2
        if is_mentioned:
            salience = 1.0
        content_lower = ctx.raw_content.lower()
        if any(w in content_lower for w in ['lol', 'lmao', 'omg', 'wait', 'no way']):
            salience += 0.2
        if len(ctx.raw_content) < 5:
            salience -= 0.1
        if snap is not None:
            salience += 0.1 * snap.familiarity

        # Self-generated goals (SERIN_VISION Growth): an actively-pursued goal
        # is persistent intent, so it deterministically raises engagement on a
        # bounded, salience-weighted curve. No RNG — the weight is read straight
        # from accumulated goal state. Goal statements are never read here, only
        # their salience, so this stays machinery, not curation.
        active_goal_statements: list[str] = []
        if self.goals_engine is not None:
            try:
                goals = self.goals_engine.pursuit_snapshot(limit=3)
                for goal in goals:
                    active_goal_statements.append(str(goal.get("statement", "")))
                if goals:
                    salience = min(1.0, salience + self._goal_salience_bonus(goals))
                    ctx.metadata["active_goals"] = active_goal_statements
            except Exception as e:  # never let goal reads break the decision
                logger.debug("goals decision boost skipped: %s", e)

        salience = max(0.0, min(1.0, salience))

        user_valence = snap.valence if snap is not None else 0.0
        user_familiarity = snap.familiarity if snap is not None else 0.0

        # Decide action
        if hard_override:
            action = "reply"
        elif self.dynamics:
            action = self.dynamics.decide_action(
                channel_id=ctx.channel_id,
                salience=salience,
                is_addressed=is_mentioned or name_in_msg,
                user_valence=user_valence,
                user_familiarity=user_familiarity,
            )
        else:
            action = "reply"

        # Execute action
        if action == "reply":
            ctx.should_respond = True
            ctx.halt_reason = ""
            try:
                await broadcast_event("decision", {
                    "user": ctx.username, "channel": ctx.channel_id[:8],
                    "channel_id": ctx.channel_id,
                    "decision": "RESPOND", "reason": "boltzmann_reply",
                    "content_preview": ctx.raw_content[:80],
                    "salience": round(salience, 2),
                    "momentum": round(self.dynamics.channels[ctx.channel_id]["momentum"], 2)
                    if self.dynamics else 0,
                })
            except Exception as e:
                logger.debug("broadcast decision event failed: %s", e)
            return ctx

        elif action == "react":
            ctx.should_respond = False
            ctx.halt_reason = "react_only"
            delay = self.dynamics.sample_reaction_delay(ctx.channel_id) if self.dynamics else 2.0
            emoji = self._pick_reaction_emoji(ctx.raw_content)
            if emoji and ctx.message:
                async def _delayed_react() -> None:
                    await asyncio.sleep(delay)
                    try:
                        await ctx.message.add_reaction(emoji)
                    except Exception as e:
                        logger.debug("add_reaction failed: %s", e)
                asyncio.create_task(_delayed_react())
            try:
                await broadcast_event("decision", {
                    "user": ctx.username, "channel": ctx.channel_id[:8],
                    "channel_id": ctx.channel_id,
                    "decision": "REACT", "reason": f"boltzmann_react ({emoji})",
                    "content_preview": ctx.raw_content[:80],
                    "salience": round(salience, 2),
                })
            except Exception as e:
                logger.debug("broadcast react event failed: %s", e)
            return ctx

        else:  # ignore
            ctx.should_respond = False
            ctx.halt_reason = "boltzmann_ignore"
            try:
                await broadcast_event("decision", {
                    "user": ctx.username, "channel": ctx.channel_id[:8],
                    "channel_id": ctx.channel_id,
                    "decision": "SKIP", "reason": "boltzmann_ignore",
                    "content_preview": ctx.raw_content[:80],
                    "salience": round(salience, 2),
                })
            except Exception as e:
                logger.debug("broadcast ignore event failed: %s", e)
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
            logger.debug("pipeline.temporal_resolved", extra={
                "user": ctx.username,
                "refs_found": len(resolved),
                "refs": resolved,
            })

        return ctx
