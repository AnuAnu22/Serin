"""
PromptAssemblyStage
-------------------
Builds the LLM prompt: system message + context block + conversation history.
Sets ctx.system_prompt, ctx.context_block, and ctx.built_messages.
"""
from __future__ import annotations

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage
from serin.messaging.response_generator import build_natural_system_prompt


class PromptAssemblyStage(PipelineStage):
    """Assembles the final messages array sent to the LLM."""

    def __init__(self, mention_translator):
        self.mention_translator = mention_translator

    async def _run(self, ctx: MessageContext) -> MessageContext:
        # Build system prompt
        ctx.system_prompt = build_natural_system_prompt()
        if ctx.tone_modifier:
            ctx.system_prompt += f"\n\nCurrent mood: {ctx.tone_modifier}"

        # Build context block from memories
        context_parts = []
        if ctx.memories:
            memory_lines = []
            for mem in ctx.memories:
                ts = (mem.get("timestamp") or "")[:10]
                memory_lines.append(f"- {mem['content']} (from {ts})")
            if memory_lines:
                context_parts.append("Relevant memories:\n" + "\n".join(memory_lines))

        if ctx.temporal_refs:
            context_parts.append(
                "Time references: " + ", ".join(ctx.temporal_refs)
            )

        if ctx.personality_context:
            context_parts.append(ctx.personality_context)

        if ctx.user_profile:
            traits = ctx.user_profile.get("personality_traits", [])[:5]
            interests = ctx.user_profile.get("interests", [])[:5]
            if traits or interests:
                profile_parts = []
                if traits:
                    profile_parts.append(f"Traits: {', '.join(traits)}")
                if interests:
                    profile_parts.append(f"Interests: {', '.join(interests)}")
                context_parts.append("User profile: " + "; ".join(profile_parts))

        ctx.context_block = "\n\n".join(context_parts)

        # Build messages array
        messages = []
        messages.append({"role": "system", "content": ctx.system_prompt})

        if ctx.context_block:
            messages.append({"role": "system", "content": ctx.context_block})

        # Add recent conversation
        for msg in ctx.recent_messages:
            role = "user"
            content = f"{msg.get('user_name', 'unknown')}: {msg.get('content', '')}"
            messages.append({"role": role, "content": content})

        # Add current message
        messages.append(
            {"role": "user", "content": f"{ctx.username}: {ctx.raw_content}"}
        )

        ctx.built_messages = messages

        logger.debug("pipeline.prompt_assembled", extra={
            "user": ctx.username,
            "system_prompt_len": len(ctx.system_prompt),
            "context_block_len": len(ctx.context_block),
            "built_messages_count": len(ctx.built_messages),
        })

        return ctx
