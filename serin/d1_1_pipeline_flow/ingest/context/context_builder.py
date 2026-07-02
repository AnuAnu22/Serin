"""
Conversation Context Builder - Human-like Memory Recall
Builds conversation context that makes the bot feel like a real person.

Enterprise-grade context building with temporal awareness integration.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from serin.d1_1_pipeline_flow.remember.temporal import (
    TemporalFormatter,
)
from serin.d1_3_state_core.logger import logger

if TYPE_CHECKING:
    from serin.d1_1_pipeline_flow.remember.qdrant import QdrantMemorySystem

_TIME_PATTERN_RE = re.compile(
    r'(last \w+day)|'
    r'(this morning|this afternoon|tonight|this evening)|'
    r'(yesterday|today|tomorrow)|'
    r'(\d+ days? ago)|'
    r'(\d+ weeks? ago)|'
    r'(a (?:few|couple) days? ago)|'
    r'(last (?:week|month|night))'
)


class ConversationContextBuilder:
    def __init__(self, memory_system: QdrantMemorySystem) -> None:
        self.memory: QdrantMemorySystem = memory_system
        self.temporal_formatter: TemporalFormatter = TemporalFormatter()

    def build_context(
        self,
        user_messages: list[dict[str, Any]],
        channel_id: str | None = None,
        query_time_hint: str | None = None,
        mood_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build structured context using type-specific retrieval.
        Each memory type gets its own query, its own limit, and its own
        section in the returned dict. No single type can dominate.
        """

        # Extract info from current messages
        participants = list(set(msg['user_id'] for msg in user_messages))
        primary_user_id = user_messages[-1]['user_id']
        primary_username = user_messages[-1]['user_name']

        # 1. Working memory — always present, from SQLite
        recent_messages = []
        if channel_id:
            recent_messages = self.memory.get_recent_conversation(
                channel_id=channel_id,
                limit=15,
            )

        # Build base query from recent messages
        query_parts = [msg['content'] for msg in user_messages[-3:]]
        search_query = " ".join(query_parts)
        logger.debug(f" Searching memories for: '{search_query[:60]}...'")

        # 2. Evidence memories — high priority, separate retrieval
        evidence_memories = self.memory.search_memories(
            query=search_query,
            user_id=primary_user_id,
            limit=3,
        )

        # 3. Episode memories (summaries) — secondary, separate retrieval
        episode_memories = self.memory.search_memories(
            query=search_query,
            user_id=primary_user_id,
            limit=2,
        )

        # 4. Regular utterance memories — lowest priority, limited to 2
        utterance_memories = self.memory.search_memories(
            query=search_query,
            user_id=primary_user_id,
            limit=2,
        )

        # Mood-based filtering: when mood is chill/low-energy, strip argument
        # memories so the model doesn't get pulled into debate mode
        if mood_state:
            tone = (mood_state.get("tone_modifier") or "").lower()
            is_chill = any(w in tone for w in ["chill", "low-energy", "straightforward", "genuine"])
            is_energetic = any(w in tone for w in ["energetic", "punchy", "sarcastic"])
            if is_chill:
                # Drop argument-like utterance memories
                argument_kw = ["lose", "lost", "win", "won", "admit", "wrong",
                               "cope", "argue", "disagree", "disagreed"]
                utterance_memories = [
                    m for m in utterance_memories
                    if not any(kw in m.get('content', '').lower() for kw in argument_kw)
                ]
            elif is_energetic:
                # Allow an extra utterance memory for debate
                utterance_memories = self.memory.search_memories(
                    query=search_query,
                    user_id=primary_user_id,
                    limit=3,
                )

        # 5. Relationships
        relationships = self.memory.get_user_relationships(
            primary_user_id, min_strength=0.3,
        )

        # 6. User profiles
        profiles = {}
        for user_id in participants:
            profile = self.memory.get_user_profile(user_id)
            if profile:
                profiles[user_id] = profile

        # 7. Facts — from FactStore, highest priority, keyword-matched to query
        facts = self.memory.get_relevant_facts(
            query=search_query,
            limit=5,
        )

        # 8. Beliefs — from BeliefStore, conclusions inferred from facts
        beliefs = self.memory.get_relevant_beliefs(
            query=search_query,
            limit=3,
        )

        return {
            'recent_conversation': recent_messages,
            'facts': facts,
            'beliefs': beliefs,
            'evidence_memories': evidence_memories,
            'episode_memories': episode_memories,
            'utterance_memories': utterance_memories,
            'profiles': profiles,
            'relationships': relationships,
            'primary_user': {
                'user_id': primary_user_id,
                'username': primary_username,
            },
        }

    def _search_with_time_range(
        self,
        query: str,
        user_id: str,
        time_range: tuple[datetime, datetime]
    ) -> list[dict[str, Any]]:
        # Get broader set of memories
        all_memories = self.memory.search_memories(
            query=query,
            user_id=user_id,
            limit=20  # Get more, then filter
        )

        start_time, end_time = time_range
        filtered = []

        for mem in all_memories:
            ts_raw = mem.get('timestamp', '')
            if not ts_raw:
                continue
            try:
                if isinstance(ts_raw, str):
                    timestamp = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                else:
                    timestamp = ts_raw
                if start_time <= timestamp <= end_time:
                    filtered.append(mem)
            except (ValueError, TypeError):
                continue

        logger.info(f"[TIME] Filtered {len(all_memories)} → {len(filtered)} memories by time range")

        return filtered[:5]  # Return top 5

    def format_context_for_llm(self, context: dict[str, Any]) -> str:
        """
        Format context as a narrative internal monologue.
        This forces the LLM to synthesize memories rather than reading a list.
        """

        narrative_parts = []

        # 1. Immediate Situation (Recent Conversation)
        if context['recent_conversation']:
            narrative_parts.append("--- CURRENT SITUATION ---")
            conv_lines = []
            for msg in context['recent_conversation'][-10:]:
                username = msg.get('username', msg.get('user_name', 'Unknown'))
                conv_lines.append(f"{username}: {msg['content']}")
            narrative_parts.append("\n".join(conv_lines))

        # 2. Internal Memory Stream (The "Brain")
        memory_stream = []

        # Relevant memories
        if context['relevant_memories']:
            memory_stream.append("I recall the following relevant details:")
            for mem in context['relevant_memories'][:4]:
                ts_raw = mem.get('timestamp', '')
                if not ts_raw:
                    memory_stream.append(f"- {mem.get('username', mem.get('user_name', 'Unknown'))} mentioned: {mem['content']}")
                    continue
                try:
                    if isinstance(ts_raw, str):
                        timestamp = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                    else:
                        timestamp = ts_raw
                    time_ref = self.temporal_formatter.format_natural(timestamp)
                except (ValueError, TypeError):
                    time_ref = "Earlier"
                memory_stream.append(f"- {time_ref}, {mem.get('username', mem.get('user_name', 'Unknown'))} mentioned: {mem['content']}")

        # User profiles (Narrative)
        profiles = context['profiles']
        if profiles:
            memory_stream.append("\nMy impressions of people here:")
            for user_id, profile in profiles.items():
                traits = profile.get('personality_traits', [])
                interests = profile.get('interests', [])

                desc = f"- {profile.get('username', profile.get('display_name', user_id))}"
                if traits:
                    desc += f" seems {', '.join(traits[:3])}"
                if interests:
                    desc += f" and is into {', '.join(interests[:3])}"
                memory_stream.append(desc)

        # Relationships
        relationships = context['relationships']
        if relationships:
            close_friends = [r['other_username'] for r in relationships if r['relationship_strength'] > 0.6]
            if close_friends:
                memory_stream.append(f"\n(I feel pretty close to {', '.join(close_friends)})")

        if memory_stream:
            narrative_parts.append("\n--- INTERNAL MEMORY STREAM ---")
            narrative_parts.append("(These are my private thoughts/memories. I should use them to inform my response naturally, without explicitly saying 'I remember'.)")
            narrative_parts.append("\n".join(memory_stream))

        return "\n\n".join(narrative_parts)

    def resolve_referents(self, current_message: str, recent_messages: list[dict[str, Any]]) -> str:
        """
        Resolve "them", "that", "it" to actual referents from recent messages.
        Makes conversation feel continuous.
        """
        message_lower = current_message.lower()

        # Check if message contains referents
        referents = ['them', 'they', 'that', 'it', 'those', 'these']
        has_referent = any(ref in message_lower for ref in referents)

        if not has_referent or len(recent_messages) < 2:
            return current_message

        # Look for entities in recent messages
        # Simple approach: extract capitalized words or @mentions
        entities = []
        for msg in recent_messages[-5:-1]:  # Last 4 messages (excluding current)
            content = msg['content']
            # Find capitalized words (likely names/nouns)
            words = content.split()
            for word in words:
                if len(word) > 2 and word[0].isupper() and word not in ['I', 'The', 'A']:
                    entities.append(word)

        if entities:
            # Most recent entity is likely referent
            likely_referent = entities[-1]
            logger.debug(f"🔗 Resolved referent to: {likely_referent}")
            # Add context hint (not replacing text, just informing LLM)
            return f"{current_message} [Note: 'them/that/it' likely refers to {likely_referent}]"

        return current_message

    def extract_time_reference_from_query(self, query: str) -> str | None:
        """
        Extract time reference from user query.

        Args:
            query: User message

        Returns:
            Time reference string if found, else None

        Examples:
            "what did we talk about last Tuesday?" → "last Tuesday"
            "do you remember this morning?" → "this morning"
        """
        match = _TIME_PATTERN_RE.search(query.lower())
        if match:
            return match.group(1)

        return None
