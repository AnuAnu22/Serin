from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage

if TYPE_CHECKING:
    from serin.messaging.context import PipelineDeps


class ConversationUpdateStage(PipelineStage):
    async def _run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
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
