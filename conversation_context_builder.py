"""
Conversation Context Builder - Human-like Memory Recall
Builds conversation context that makes the bot feel like a real person.

Enterprise-grade context building with temporal awareness integration.
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from logger_config import logger
from temporal_context import TemporalFormatter, parse_time, get_time_range


class ConversationContextBuilder:
    def __init__(self, memory_system):
        self.memory = memory_system
        self.temporal_formatter = TemporalFormatter()
    
    def build_context(
        self,
        user_messages: List[Dict],
        channel_id: Optional[str] = None,
        query_time_hint: Optional[str] = None
    ) -> Dict:
        """
        Build context for LLM response.
        Makes the bot feel like it's actually remembering, not searching a database.
        
        Args:
            user_messages: Current conversation messages
            channel_id: Channel ID for filtering
            query_time_hint: Time reference from user query (e.g., "last Tuesday")
        
        Returns:
            Context dict with memories, profiles, relationships
        """
        
        # Extract info from current messages
        participants = list(set(msg['user_id'] for msg in user_messages))
        primary_user_id = user_messages[-1]['user_id']
        primary_username = user_messages[-1]['user_name']
        
        # Get recent conversation history (sliding window)
        recent_messages = self.memory.get_recent_conversation(
            channel_id=channel_id,
            limit=15
        )
        
        # Build search query from recent messages
        query_parts = []
        for msg in user_messages[-3:]:  # Last 3 messages
            query_parts.append(msg['content'])
        search_query = " ".join(query_parts)
        
        logger.debug(f"🔍 Searching memories for: '{search_query[:60]}...'")
        
        # TIER 5: Check for time reference in query
        time_range = None
        if query_time_hint:
            time_range = get_time_range(query_time_hint)
            if time_range:
                logger.info(f"⏰ Time range filter: {time_range[0]} to {time_range[1]}")
        
        # Search semantic memories (with optional time filtering)
        if time_range:
            # Filter by time range (need to add this to memory_system)
            relevant_memories = self._search_with_time_range(
                search_query,
                primary_user_id,
                time_range
            )
        else:
            relevant_memories = self.memory.search_memories(
                query=search_query,
                user_id=primary_user_id,
                n_results=5
            )
        
        logger.info(f"💭 Found {len(relevant_memories)} relevant memories")
        
        # Get user profiles
        profiles = {}
        for user_id in participants:
            profile = self.memory.get_user_profile(user_id)
            if profile:
                profiles[user_id] = profile
        
        # Get relationships
        relationships = self.memory.get_user_relationships(primary_user_id, min_strength=0.3)
        
        # Build natural context sections
        return {
            'recent_conversation': recent_messages,
            'relevant_memories': relevant_memories,
            'profiles': profiles,
            'relationships': relationships,
            'primary_user': {
                'user_id': primary_user_id,
                'username': primary_username
            },
            'time_context': {
                'query_time_hint': query_time_hint,
                'time_range': time_range
            }
        }
    
    def _search_with_time_range(
        self,
        query: str,
        user_id: str,
        time_range: Tuple[datetime, datetime]
    ) -> List[Dict]:
        """
        Search memories within specific time range.
        
        Args:
            query: Search query
            user_id: User ID filter
            time_range: (start_time, end_time) tuple
        
        Returns:
            List of memories within time range
        """
        # Get broader set of memories
        all_memories = self.memory.search_memories(
            query=query,
            user_id=user_id,
            n_results=20  # Get more, then filter
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
        
        logger.info(f"⏰ Filtered {len(all_memories)} → {len(filtered)} memories by time range")
        
        return filtered[:5]  # Return top 5
    
    def format_context_for_llm(self, context: Dict) -> str:
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
    
    def resolve_referents(self, current_message: str, recent_messages: List[Dict]) -> str:
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
    
    def extract_time_reference_from_query(self, query: str) -> Optional[str]:
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
        query_lower = query.lower()
        
        # Common time reference patterns
        time_patterns = [
            r'(last \w+day)',           # last Tuesday, last Monday
            r'(this morning|this afternoon|tonight|this evening)',
            r'(yesterday|today|tomorrow)',
            r'(\d+ days? ago)',
            r'(\d+ weeks? ago)',
            r'(a (few|couple) days? ago)',
            r'(last (week|month|night))',
        ]
        
        for pattern in time_patterns:
            import re
            match = re.search(pattern, query_lower)
            if match:
                return match.group(1)
        
        return None