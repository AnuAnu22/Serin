from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import discord

from serin.core.logger import logger


# ============================================================================
# Data contracts
# ============================================================================

@dataclass
class MessageContext:
    """Mutable context passed through each pipeline stage."""
    batch: list
    channel: Any = None
    user_messages: list = field(default_factory=list)
    is_instruction: bool = False
    bot_mentioned: bool = False
    context: dict = field(default_factory=dict)
    formatted_context: str = ""
    conv_analysis: dict = field(default_factory=dict)
    preference_context: Optional[str] = None
    voice_info: Optional[dict] = None
    resolved_message: str = ""
    tone_modifier: str = ""
    length_analysis: dict = field(default_factory=dict)
    primary_user_id: str = ""
    fatigue_level: float = 0.0
    detected_topic: Optional[str] = None
    active_search_results: list = field(default_factory=list)
    response: Optional[str] = None
    should_halt: bool = False


@dataclass
class PipelineDeps:
    """All external dependencies injected into the pipeline."""
    memory: Any
    context_builder: Any
    bot_personality: Any
    response_controller: Any
    personality: Any
    voice_tracker: Any
    conversation_analyzer: Any
    analyzer: Any  # SentimentIntensityAnalyzer
    pending_visual_contexts: Dict[int, str]
    active_search: Optional[Any]
    voice_action_decider: Optional[Any]
    voice_action_callback: Optional[Any]
    mention_translator: Any
    current_state: Dict[str, Any]
    stats: Dict[str, int]
    last_bot_response: Optional[str]
    last_bot_response_channel: Optional[str]


# ============================================================================
# Pipeline stage interface
# ============================================================================

class PipelineStage(ABC):
    @abstractmethod
    async def run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        ...


class MessagePipeline:
    def __init__(self, stages: List[PipelineStage], deps: PipelineDeps):
        self.stages = stages
        self.deps = deps

    async def process(self, ctx: MessageContext) -> MessageContext:
        for stage in self.stages:
            await stage.run(ctx, self.deps)
            if ctx.should_halt:
                break
        return ctx


# ============================================================================
# Stage 1: Prepare messages from raw batch
# ============================================================================

class MessagePreparationStage(PipelineStage):
    async def run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        batch = [m for m in ctx.batch if not getattr(m.author, "bot", False)]
        if not batch:
            ctx.should_halt = True
            return

        ctx.channel = batch[0].channel

        user_messages = []
        for msg in batch:
            content = deps.mention_translator.clean_for_bot(msg.content, msg)
            if msg.attachments:
                has_image = any(
                    a.content_type and a.content_type.startswith('image/')
                    for a in msg.attachments
                )
                if has_image:
                    content += " [User posted an image]"

            payload = {
                'user_id': str(msg.author.id),
                'user_name': msg.author.display_name,
                'content': content,
                'timestamp': msg.created_at.isoformat()
            }

            if msg.id in deps.pending_visual_contexts:
                payload['image_url'] = deps.pending_visual_contexts[msg.id]
                del deps.pending_visual_contexts[msg.id]

            user_messages.append(payload)

        ctx.user_messages = user_messages

        # Admin instruction check
        last_msg_content = ctx.user_messages[-1]['content']
        last_msg_user = ctx.user_messages[-1]['user_name']
        is_creator = (
            deps.response_controller.creator_id
            and ctx.user_messages[-1]['user_id'] == deps.response_controller.creator_id
        )

        if last_msg_content.startswith('/instruct'):
            if 'rin' in last_msg_user.lower() or is_creator:
                logger.info(f"Admin instruction detected from {last_msg_user}")
                ctx.is_instruction = True
                ctx.user_messages[-1]['content'] = last_msg_content.replace('/instruct', '', 1).strip()
            else:
                logger.warning(f"Unauthorized /instruct attempt from {last_msg_user}")
                ctx.should_halt = True
                return


# ============================================================================
# Stage 2: Memory retrieval + pollution filter
# ============================================================================

class MemoryRetrievalStage(PipelineStage):
    GARBAGE_PATTERNS = [
        "We are given", "We must write", "CRITICAL RULES", "CRITICAL:",
        "one sentence", "Summary:", "Task:", "INSTRUCTIONS",
        "### FINAL", "[the ", "template", "example",
        "Output Format", "JSON", "search_needed", "query:",
        "username followed by", "third person"
    ]

    async def run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        logger.debug("Building enhanced context...")

        ctx.context = deps.context_builder.build_context(
            user_messages=ctx.user_messages,
            channel_id=str(ctx.channel.id)
        )

        # Filter polluted memories
        clean_memories = []
        for mem in ctx.context.get('relevant_memories', []):
            content = mem.get('content', '')
            is_garbage = any(
                pattern.lower() in content.lower()
                for pattern in self.GARBAGE_PATTERNS
            )
            if is_garbage:
                logger.warning(f"Filtered polluted memory: {content[:50]}...")
                continue
            clean_memories.append(mem)
        ctx.context['relevant_memories'] = clean_memories

        deps.stats['context_improvements'] += 1
        logger.info("Using ConversationContextBuilder for context")
        self._log_context(ctx)

    def _log_context(self, ctx: MessageContext) -> None:
        logger.info(f"Recent messages: {len(ctx.context.get('recent_conversation', []))}")
        logger.info(f"Relevant memories: {len(ctx.context.get('relevant_memories', []))}")
        logger.info(f"User profiles: {len(ctx.context.get('profiles', {}))}")
        logger.info(f"Relationships: {len(ctx.context.get('relationships', []))}")


# ============================================================================
# Stage 3: Conversation state updates (voice, analysis, mood, personality)
# ============================================================================

class ConversationUpdateStage(PipelineStage):
    async def run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        ctx.primary_user_id = ctx.user_messages[-1]['user_id']
        ctx.voice_info = deps.voice_tracker.get_voice_info(ctx.primary_user_id)

        # Voice join reaction
        if ctx.voice_info:
            duration = ctx.voice_info.get('duration_minutes', 0)
            if duration < 2:
                from serin.utils.debug_logger import log_context
                from voice.voice_tracker import get_voice_join_reaction
                reaction = get_voice_join_reaction()
                if reaction:
                    await ctx.channel.send(reaction)
                    await asyncio.sleep(random.uniform(1.0, 2.0))

        # Message length analysis
        from serin.messaging.long_message import analyze_message_length, get_length_handler
        ctx.length_analysis = analyze_message_length(ctx.user_messages[-1]['content'])
        length_handler = get_length_handler()
        personality_dict = deps.personality.__dict__ if hasattr(deps.personality, '__dict__') else None

        if length_handler.should_react_to_length(ctx.length_analysis, personality_dict):
            reaction = length_handler.get_length_reaction(ctx.length_analysis)
            if reaction:
                await ctx.channel.send(reaction)
                await asyncio.sleep(random.uniform(1.0, 2.0))

        # Topic fatigue
        from serin.personality.topic_fatigue import get_fatigue_tracker
        ctx.detected_topic = self._detect_topic(ctx.user_messages[-1]['content'])
        fatigue_tracker = get_fatigue_tracker()
        if ctx.detected_topic:
            fatigue_tracker.track_topic(str(ctx.channel.id), ctx.detected_topic)
            ctx.fatigue_level = fatigue_tracker.get_topic_fatigue_level(
                str(ctx.channel.id), ctx.detected_topic
            )
            if ctx.fatigue_level > 0.3:
                modified = fatigue_tracker.apply_fatigue_to_personality(
                    deps.personality.__dict__, ctx.fatigue_level
                )
                for key, value in modified.items():
                    setattr(deps.personality, key, value)

        # Update relationships
        participants = list(set(um['user_id'] for um in ctx.user_messages))
        if len(participants) > 1:
            for i, user_a in enumerate(participants):
                for user_b in participants[i + 1:]:
                    deps.memory.update_relationship(user_a, user_b, 'message')

        # Conversation mood
        sentiment_scores = [
            deps.analyzer.polarity_scores(msg['content'])['compound']
            for msg in ctx.user_messages
        ]
        deps.response_controller.update_conversation_mood(
            str(ctx.channel.id), ctx.user_messages, sentiment_scores
        )

        # Personality update
        primary_profile = ctx.context.get('profiles', {}).get(ctx.primary_user_id, {})
        primary_traits = primary_profile.get('personality_traits', [])
        conversation_mood = deps.response_controller.conversation_mood.get(str(ctx.channel.id), 'neutral')

        deps.personality.update_from_conversation(
            conversation_mood, primary_traits, datetime.now().hour
        )

        # Conversation analysis
        ctx.conv_analysis = deps.conversation_analyzer.analyze_conversation_flow(
            ctx.user_messages, str(ctx.channel.id)
        )
        logger.info(f"Conversation: {ctx.conv_analysis['conversation_type']}")
        if ctx.conv_analysis['current_topic']:
            logger.info(f"Topic: {ctx.conv_analysis['current_topic']}")

        # Preference triggers
        preference_trigger = deps.bot_personality.detect_topic_in_message(
            ctx.user_messages[-1]['content']
        )
        if preference_trigger:
            category, item = preference_trigger
            ctx.preference_context = deps.bot_personality.express_preference(category, item)
            logger.debug(f"Preference: {ctx.preference_context}")

    def _detect_topic(self, content: str) -> Optional[str]:
        # Inline from the original manager
        topic_map = {
            'games': ['game', 'play', 'gaming', 'steam', 'xbox', 'playstation', 'nintendo'],
            'tech': ['code', 'programming', 'python', 'ai', 'computer', 'linux'],
            'music': ['song', 'music', 'band', 'album', 'sing'],
            'movies': ['movie', 'film', 'watch', 'netflix', 'cinema'],
            'anime': ['anime', 'manga', 'weeb', 'japanese'],
        }
        content_lower = content.lower()
        for topic, keywords in topic_map.items():
            if any(kw in content_lower for kw in keywords):
                return topic
        return None


# ============================================================================
# Stage 4: Response decision
# ============================================================================

class ResponseDecisionStage(PipelineStage):
    async def run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        should_respond, reason = deps.response_controller.should_respond(
            message_content=ctx.user_messages[-1]['content'],
            channel_id=str(ctx.channel.id),
            bot_mentioned=ctx.bot_mentioned or ctx.is_instruction,
            user_id=ctx.primary_user_id,
            recent_messages=ctx.context.get('recent_conversation', [])
        )

        if not should_respond and not ctx.is_instruction:
            logger.info(f"Skipping response (reason: {reason})")
            ctx.should_halt = True
            return

        logger.info(f"Responding (reason: {reason})")


# ============================================================================
# Stage 5: Context assembly (format context + personality + voice info)
# ============================================================================

class ContextAssemblyStage(PipelineStage):
    async def run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        ctx.formatted_context = deps.context_builder.format_context_for_llm(ctx.context)

        personality_context = deps.bot_personality.get_personality_context()
        if personality_context:
            ctx.formatted_context += f"\n\n{personality_context}"

        if ctx.preference_context:
            ctx.formatted_context += f"\n\nNote: You think {ctx.preference_context}"

        if ctx.voice_info:
            channel_name = ctx.voice_info.get('channel_name', 'voice channel')
            duration = ctx.voice_info.get('duration_minutes', 0)
            ctx.formatted_context += (
                f"\n\n[Note: {ctx.user_messages[-1]['user_name']} is "
                f"currently in '{channel_name}' ({duration} min)]"
            )

        ctx.resolved_message = ctx.user_messages[-1]['content']
        ctx.tone_modifier = deps.personality.get_tone_modifier()

        self._log_debug(ctx)

    def _log_debug(self, ctx: MessageContext) -> None:
        logger.info("=" * 60)
        logger.info("ENHANCED CONTEXT PREPARED")
        logger.info("=" * 60)
        logger.info(f"Recent messages: {len(ctx.context.get('recent_conversation', []))}")
        logger.info(f"Relevant memories: {len(ctx.context.get('relevant_memories', []))}")
        logger.info(f"Conversation mood: {deps_mood(ctx)}")
        logger.info(f"Tone modifier: {ctx.tone_modifier}")
        logger.info("=" * 60)

        # Full prompt debug
        logger.info("=" * 80)
        logger.info("COMPLETE PROMPT BEING SENT TO LLM")
        logger.info("=" * 80)
        for i, msg in enumerate(ctx.user_messages):
            logger.info(f"  [{i}] {msg['user_name']}: {msg['content'][:100]}...")
        logger.info(f"\nFormatted context length: {len(ctx.formatted_context)} chars")
        logger.info(f"\nFormatted context:\n{ctx.formatted_context}")
        logger.info(f"\nTone modifier: {ctx.tone_modifier}")
        logger.info(f"Message complexity: {ctx.length_analysis.get('complexity', 'unknown')}")
        logger.info(f"Channel ID: {ctx.channel.id}")
        logger.info(f"Channel name: {ctx.channel.name}")
        logger.info("=" * 80)
        logger.info("SENDING TO LLM")
        logger.info("=" * 80)


def deps_mood(ctx: MessageContext) -> str:
    return 'unknown'


# ============================================================================
# Stage 6: Active search (thinking loop)
# ============================================================================

class ActiveSearchStage(PipelineStage):
    async def run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        if not deps.active_search:
            return

        logger.info("Entering Thinking Loop...")
        max_loops = 2
        loop_count = 0
        accumulated_results = ""

        while loop_count < max_loops:
            needs_search, query, reason = await deps.active_search.analyze_need_to_search(
                user_message=ctx.user_messages[-1]['content'],
                recent_context=ctx.formatted_context,
                previous_results=accumulated_results if loop_count > 0 else None
            )

            if not needs_search or not query:
                logger.info(f"Thinking complete: No further search needed ({reason})")
                break

            logger.info(f"Thought (Iter {loop_count + 1}): search for '{query}' ({reason})")

            new_results = deps.memory.search_memories(
                query=query,
                user_id=ctx.primary_user_id,
                n_results=3
            )
            logger.info(f"Found {len(new_results)} results")

            if new_results:
                ctx.formatted_context += f"\n\n--- ACTIVE RECALL (Iteration {loop_count + 1}) ---\n"
                ctx.formatted_context += f"Query: {query}\n"
                for mem in new_results:
                    ts = (mem.get('timestamp') or '')[:10]
                    ctx.formatted_context += f"- {mem['content']} (from {ts})\n"

                accumulated_results += f"\nResults for '{query}':\n"
                for mem in new_results:
                    ts = (mem.get('timestamp') or '')[:10]
                    accumulated_results += f"- {mem['content']} (from {ts})\n"

                ctx.active_search_results.extend(new_results)
            else:
                logger.info("   (No results found)")
                accumulated_results += f"\nResults for '{query}': None found.\n"

            loop_count += 1


# ============================================================================
# Stage 7: Voice action decision
# ============================================================================

class VoiceActionStage(PipelineStage):
    async def run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        if not deps.voice_action_decider or not deps.voice_action_callback:
            return
        if deps.current_state.get('abort_flag'):
            return

        try:
            voice_decision = await deps.voice_action_decider.decide(
                user_message=ctx.user_messages[-1]['content'],
                context=ctx.formatted_context,
                personality_state=deps.personality.__dict__,
            )
            if voice_decision and voice_decision['action'] in ('join', 'leave'):
                result = await deps.voice_action_callback(
                    voice_decision,
                    ctx.primary_user_id,
                    ctx.channel.guild.id,
                )
                if result.get('executed'):
                    ctx.formatted_context += (
                        f"\n\n[System: Serin {voice_decision['action']}ed the voice channel "
                        f"because: {voice_decision.get('reason', 'unknown')}]"
                    )
                elif result.get('message') == 'user_not_in_vc':
                    ctx.formatted_context += (
                        "\n\n[System: Serin tried to join the user's voice channel "
                        "but the user is not currently in one. Serin should respond naturally.]"
                    )
        except Exception as e:
            logger.error(f"Voice action error: {e}")
            ctx.formatted_context += (
                "\n\n[System: Serin could not decide on a voice action due to an error."
                " No action was taken. Do not assume Serin joined or left any voice channel.]"
            )


# ============================================================================
# Stage 8: Response generation and sending
# ============================================================================

class GenerationStage(PipelineStage):
    async def run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        deps.current_state['abort_flag'] = False

        from serin.messaging.response_generator import get_response_natural

        response = await get_response_natural(
            current_messages=ctx.user_messages,
            context=ctx.formatted_context,
            resolved_last_message=ctx.resolved_message,
            tone_modifier=ctx.tone_modifier,
            personality_state=deps.personality.__dict__,
            message_complexity=ctx.length_analysis.get('complexity', 'medium'),
            is_instruction=ctx.is_instruction,
        )

        if deps.current_state.get('abort_flag'):
            logger.warning("Response generation aborted by user!")
            deps.current_state['status'] = 'IDLE'
            deps.current_state['current_prompt'] = None
            ctx.should_halt = True
            return

        if not response or not response.strip():
            logger.warning("Empty response generated, not sending")
            ctx.should_halt = True
            return

        if len(response) > 2000:
            response = response[:1997] + "..."

        response = deps.mention_translator.restore_for_discord(response, ctx.channel.guild)

        deps.current_state['status'] = 'SENDING'

        await deps.response_controller.send_with_typing(
            ctx.channel,
            response,
            simulate_typing=True,
            message_complexity=ctx.length_analysis.get('complexity', 'medium'),
            has_question='?' in ctx.user_messages[-1]['content']
        )

        deps.response_controller.mark_response(str(ctx.channel.id))

        deps.stats['responses_generated'] += 1
        logger.info(f"Response sent: '{response[:60]}...'")

        ctx.response = response
