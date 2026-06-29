"""
Response Controller - Makes bot feel human
- Decides when to respond (selective)
- Adds realistic timing and typing indicators
- Tracks conversation mood/energy

FIXED: Bot name detection in messages
"""
import random
import asyncio
from typing import Dict, List, Optional, Any, Coroutine
from datetime import datetime, timedelta
from logger_config import logger

import discord


class ResponseController:
    def __init__(self):
        self.last_response_time = {}  # channel_id -> timestamp
        self.conversation_mood = {}   # channel_id -> mood state
        self.message_buffer = {}      # channel_id -> message count since last response
        self.active_conversations = {}  # channel_id -> {user_id, last_message_time, message_count}
        
        # Bot name variations to detect
        self.bot_name_variations = [
            'serin',
            'serін',  # Cyrillic lookalike
            '@serin',
            'serine',
            'Serin'
        ]
        
        # Creator ID (Rin) - should ALWAYS be responsive to creator
        self.creator_id = None  # Will be set when bot sees Rin
        
        # Event broadcaster (for WebSocket)
        self.broadcaster = None

    def set_broadcaster(self, broadcast_func: Any) -> None:
        """Set broadcaster function for real-time decisions"""
        self.broadcaster = broadcast_func
        
    def set_creator_id(self, user_id: str) -> None:
        """Set creator ID for priority responses"""
        self.creator_id = user_id
        logger.info(f"✅ Creator ID set: {user_id}")

    def _message_mentions_bot(self, message_content: str) -> bool:
        """Check if message mentions bot by name (case-insensitive)"""
        content_lower = message_content.lower()
        
        for name in self.bot_name_variations:
            if name.lower() in content_lower:
                logger.info(f"🎯 Bot name '{name}' detected in message")
                return True
        
        return False
        
    def _is_in_active_conversation(self, channel_id: str, user_id: str) -> bool:
        """
        Check if user is in active conversation with bot.
        Conversation is active if:
        - Bot responded to this user in last 2 minutes
        - User has sent 2+ messages in last minute
        """
        if channel_id not in self.active_conversations:
            return False
        
        conv = self.active_conversations[channel_id]
        
        # Check if same user
        if conv.get('user_id') != user_id:
            return False
        
        # Check if conversation is still fresh (within 2 minutes)
        time_since = (datetime.now() - conv['last_message_time']).total_seconds()
        if time_since > 120:  # 2 minutes
            return False
        
        return True

    
    def _start_conversation(self, channel_id: str, user_id: str) -> None:
        """Mark start of active conversation"""
        self.active_conversations[channel_id] = {
            'user_id': user_id,
            'last_message_time': datetime.now(),
            'message_count': 1
        }
        logger.debug(f"💬 Started conversation with user {user_id} in channel {channel_id}")
    
    def _update_conversation(self, channel_id: str, user_id: str) -> None:
        """Update active conversation"""
        if channel_id in self.active_conversations:
            conv = self.active_conversations[channel_id]
            if conv['user_id'] == user_id:
                conv['last_message_time'] = datetime.now()
                conv['message_count'] = conv.get('message_count', 0) + 1
        
    def should_respond(
        self,
        message_content: str,
        channel_id: str,
        bot_mentioned: bool,
        user_id: str,
        recent_messages: List[Dict]
    ) -> tuple[bool, str]:
        """
        Decide if bot should respond to this message.
        Returns: (should_respond: bool, reason: str)
        
        HUMAN-LIKE LOGIC:
        1. Always respond to creator (Rin)
        2. Always respond if mentioned
        3. Stay engaged in active conversations
        4. Be selective when not in conversation
        """
        
        # Check if this is the creator (by username)
        is_creator = False
        if recent_messages:
            last_msg_user = recent_messages[-1].get('user_name', '').lower()
            if 'rin' in last_msg_user:
                is_creator = True
                if not self.creator_id:
                    self.set_creator_id(user_id)
        
        # Also check by user_id if we know creator
        if self.creator_id and user_id == self.creator_id:
            is_creator = True
        
        logger.debug("=" * 60)
        logger.debug("🔍 RESPONSE DECISION")
        logger.debug(f"User: {user_id} (Creator: {is_creator})")
        logger.debug(f"Message: '{message_content[:60]}...'")
        logger.debug(f"Mentioned: {bot_mentioned}")
        logger.debug(f"In conversation: {self._is_in_active_conversation(channel_id, user_id)}")
        logger.debug("=" * 60)
        
        # PRIORITY 1: ALWAYS respond to creator
        if is_creator:
            self._start_conversation(channel_id, user_id)
            self._broadcast_decision("ACCEPTED", "creator_message", channel_id)
            return True, "creator_message"
        
        # PRIORITY 2: ALWAYS respond if mentioned via Discord @mention
        if bot_mentioned:
            self._start_conversation(channel_id, user_id)
            self._broadcast_decision("ACCEPTED", "bot_mentioned_discord", channel_id)
            return True, "bot_mentioned_discord"
        
        # PRIORITY 3: ALWAYS respond if bot name appears in message
        if self._message_mentions_bot(message_content):
            self._start_conversation(channel_id, user_id)
            self._broadcast_decision("ACCEPTED", "bot_name_in_message", channel_id)
            return True, "bot_name_in_message"
        
        # PRIORITY 4: Stay engaged in active conversations (95% response rate)
        if self._is_in_active_conversation(channel_id, user_id):
            self._update_conversation(channel_id, user_id)
            
            # Very high chance to respond when in conversation
            if random.random() < 0.95:
                self._broadcast_decision("ACCEPTED", "active_conversation", channel_id)
                return True, "active_conversation"
            else:
                # 5% chance to naturally end conversation
                self._broadcast_decision("SKIPPED", "conversation_natural_end", channel_id)
                return False, "conversation_natural_end"
        
        # Check message length
        content_len = len(message_content.strip())
        
        # Ignore very short messages sometimes (but less aggressively)
        if content_len < 5:
            if random.random() < 0.3:  # Reduced from 0.5
                self._broadcast_decision("SKIPPED", "too_short", channel_id)
                return False, "too_short"
        
        # Single-word messages - be more lenient
        words = message_content.split()
        if len(words) == 1:
            if random.random() < 0.4:  # Reduced from 0.7
                self._broadcast_decision("SKIPPED", "single_word", channel_id)
                return False, "single_word"
        
        # Check if it's a private conversation between others
        if len(recent_messages) >= 3:
            last_three_users = [m.get('user_id') for m in recent_messages[-3:]]
            unique_users = set(last_three_users)
            
            # If last 3 messages are from same 2 people (and we're not one of them)
            if len(unique_users) == 2 and user_id in unique_users:
                # Check if bot was in the conversation
                bot_in_conv = any(m.get('user_name', '').lower() == 'serin' for m in recent_messages[-5:])
                
                if not bot_in_conv:
                    # 50% chance to stay out (reduced from 70%)
                    if random.random() < 0.5:
                        self._broadcast_decision("SKIPPED", "private_conversation", channel_id)
                        return False, "private_conversation"
        
        # Check response frequency - but be more lenient
        if channel_id in self.last_response_time:
            time_since_last = (datetime.now() - self.last_response_time[channel_id]).total_seconds()
            
            # If responded less than 5 seconds ago, be selective
            if time_since_last < 5:  # Reduced from 10
                if random.random() < 0.3:  # Reduced from 0.5
                    self._broadcast_decision("SKIPPED", "too_frequent", channel_id)
                    return False, "too_frequent"
        
        # Check if message is a question (ALWAYS respond)
        if '?' in message_content:
            self._start_conversation(channel_id, user_id)
            self._broadcast_decision("ACCEPTED", "question_asked", channel_id)
            return True, "question_asked"
        
        # Check if message is addressing the channel generally
        greetings = ['hey everyone', 'hi all', 'sup guys', 'anyone', 'hey guys', 'yo', 'sup']
        if any(greeting in message_content.lower() for greeting in greetings):
            # 90% chance to respond to general messages
            if random.random() < 0.9:
                self._start_conversation(channel_id, user_id)
                self._broadcast_decision("ACCEPTED", "general_address", channel_id)
                return True, "general_address"
            self._broadcast_decision("SKIPPED", "general_skip", channel_id)
            return False, "general_skip"
        
        # Check if user is trying to engage (multiple messages in a row)
        if len(recent_messages) >= 3:
            last_three_users = [m.get('user_id') for m in recent_messages[-3:]]
            # If same user sent last 2-3 messages, they're trying to talk
            if last_three_users[-1] == last_three_users[-2] == user_id:
                # 90% chance to respond if someone is clearly trying to engage
                if random.random() < 0.9:
                    self._start_conversation(channel_id, user_id)
                    self._broadcast_decision("ACCEPTED", "user_engaging", channel_id)
                    return True, "user_engaging"
        
        # Random response rate based on conversation energy
        mood = self.conversation_mood.get(channel_id, 'neutral')
        
        if mood == 'energetic':
            respond_chance = 0.85  # Increased from 0.9
        elif mood == 'chill':
            respond_chance = 0.75  # Increased from 0.7
        else:  # neutral
            respond_chance = 0.80  # Same as before
        
        if random.random() < respond_chance:
            # Start conversation on response
            self._start_conversation(channel_id, user_id)
            self._broadcast_decision("ACCEPTED", f"random_{mood}", channel_id)
            return True, f"random_{mood}"
        
        self._broadcast_decision("SKIPPED", "selective_skip", channel_id)
        return False, "selective_skip"

    def _broadcast_decision(self, status: str, reason: str, channel_id: str) -> None:
        """Broadcast decision to websocket"""
        if self.broadcaster:
            try:
                data = {
                    "type": "decision",
                    "status": status,
                    "reason": reason,
                    "time": datetime.now().strftime("%H:%M:%S")
                }
                # Create task to avoid awaiting (fire and forget)
                asyncio.create_task(self.broadcaster('decision', data))
            except Exception as e:
                logger.error(f"Failed to broadcast decision: {e}")
    
    def calculate_typing_delay(
        self,
        response_length: int,
        message_complexity: str = "simple",
        has_question: bool = False
    ) -> float:
        """
        Calculate realistic typing delay based on response length and context.
        Total delay is capped at 1-10 seconds for snappy feel.
        """
        words = response_length / 5
        wps = random.uniform(1.2, 2.0)
        base_delay = words / wps

        # Base thinking time — short and snappy
        thinking_time = random.uniform(0.3, 1.0)

        # Add extra thinking for complex questions
        if has_question:
            thinking_time += random.uniform(0.5, 1.5)

        # Adjust for message complexity
        if message_complexity == "complex":
            thinking_time += random.uniform(0.5, 2.0)
        elif message_complexity == "medium":
            thinking_time += random.uniform(0.3, 1.0)

        # 10% chance for "types and deletes" pause
        if random.random() < 0.1:
            thinking_time += random.uniform(0.5, 2.0)

        total = thinking_time + base_delay

        min_delay = 1.0
        max_delay = 10.0

        return max(min_delay, min(total, max_delay))
    
    def update_conversation_mood(
        self,
        channel_id: str,
        recent_messages: List[Dict],
        sentiment_scores: List[float]
    ) -> None:
        """Update conversation mood/energy level"""
        if not recent_messages or not sentiment_scores:
            return
        
        # Calculate average sentiment
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
        
        # Calculate message frequency
        if len(recent_messages) >= 2:
            # Handle both string and datetime timestamps
            def safe_datetime_convert(timestamp):
                if isinstance(timestamp, str):
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return timestamp
            
            time_range = (
                safe_datetime_convert(recent_messages[-1]['timestamp']) -
                safe_datetime_convert(recent_messages[0]['timestamp'])
            ).total_seconds() / 60
            
            msg_per_min = len(recent_messages) / max(time_range, 1)
        else:
            msg_per_min = 0
        
        # Determine mood
        if msg_per_min > 2 and avg_sentiment > 0.2:
            mood = 'energetic'
        elif msg_per_min < 0.5 or abs(avg_sentiment) < 0.1:
            mood = 'chill'
        else:
            mood = 'neutral'
        
        self.conversation_mood[channel_id] = mood
        logger.debug(f"📊 Conversation mood: {mood} (msgs/min: {msg_per_min:.1f})")
    
    def mark_response(self, channel_id: str) -> None:
        """Mark that bot has responded"""
        self.last_response_time[channel_id] = datetime.now()
        self.message_buffer[channel_id] = 0
    
    def should_split_message(self, response: str) -> bool:
        """Decide if response should be split"""
        sentences = response.split('. ')
        
        if len(sentences) >= 3 and random.random() < 0.4:
            return True
        
        return False
    
    def split_response(self, response: str) -> List[str]:
        """Split response into multiple messages"""
        sentences = response.split('. ')
        
        if len(sentences) < 2:
            return [response]
        
        messages = []
        current = ""
        
        for i, sentence in enumerate(sentences):
            if current:
                current += ". " + sentence
            else:
                current = sentence
            
            if random.random() < 0.6 or i == len(sentences) - 1:
                if current:
                    messages.append(current.strip())
                current = ""
        
        if current:
            messages.append(current.strip())
        
        return messages if len(messages) > 1 else [response]
    
    async def send_with_typing(
        self,
        channel: discord.TextChannel,
        response: str,
        simulate_typing: bool = True,
        message_complexity: str = "simple",
        has_question: bool = False   
    ) -> None:
        """Send message with realistic typing simulation"""
        if not simulate_typing:
            await channel.send(response)
            return
        
        if self.should_split_message(response):
            messages = self.split_response(response)
            
            for i, msg in enumerate(messages):
                delay = self.calculate_typing_delay(
                    len(msg),
                    message_complexity=message_complexity,
                    has_question=has_question
                )
                
                async with channel.typing():
                    await asyncio.sleep(delay)
                
                await channel.send(msg)
                
                if i < len(messages) - 1:
                    await asyncio.sleep(random.uniform(0.5, 1.5))
        
        else:
            delay = self.calculate_typing_delay(
                len(response),
                message_complexity=message_complexity,
                has_question=has_question
            )
            
            async with channel.typing():
                await asyncio.sleep(delay)
            await channel.send(response)


class PersonalityState:
    """Tracks bot's personality state"""
    
    def __init__(self) -> None:
        self.energy_level: float = 0.5
        self.sass_level: float = 0.5
        self.engagement: float = 0.5
        self.last_update: datetime = datetime.now()
    
    def update_from_conversation(
        self,
        conversation_mood: str,
        user_traits: List[str],
        time_of_day: int
    ) -> None:
        """Update personality state"""
        # Energy varies by time of day
        if 0 <= time_of_day < 6:
            self.energy_level = max(0.2, self.energy_level - 0.1)
        elif 6 <= time_of_day < 12:
            self.energy_level = min(0.8, self.energy_level + 0.1)
        elif 12 <= time_of_day < 18:
            self.energy_level = 0.7
        else:
            self.energy_level = 0.6
        
        # Match conversation mood
        if conversation_mood == 'energetic':
            self.energy_level = min(1.0, self.energy_level + 0.2)
            self.engagement = min(1.0, self.engagement + 0.1)
        elif conversation_mood == 'chill':
            self.energy_level = max(0.7, self.energy_level - 0.1)
            self.engagement = max(0.8, self.engagement - 0.1)
        
        # Adapt sass level
        if 'humorous' in user_traits:
            self.sass_level = min(0.8, self.sass_level + 0.1)
        if 'polite' in user_traits:
            self.sass_level = max(0.3, self.sass_level - 0.1)
        
        # Natural decay towards baseline
        hours_since_update = (datetime.now() - self.last_update).total_seconds() / 3600
        if hours_since_update > 1:
            self.energy_level += (0.5 - self.energy_level) * 0.1
            self.sass_level += (0.5 - self.sass_level) * 0.1
            self.engagement += (0.5 - self.engagement) * 0.1
        
        self.last_update = datetime.now()
        
        logger.debug(
            f"Personality: "
            f"energy={self.energy_level:.2f}, "
            f"sass={self.sass_level:.2f}, "
            f"engagement={self.engagement:.2f}"
        )
    
    def get_tone_modifier(self) -> str:
        """Get tone guidance for LLM"""
        modifiers: List[str] = []
        
        if self.energy_level > 0.65:
            modifiers.append("Be energetic and punchy")
        elif self.energy_level < 0.35:
            modifiers.append("Be chill and low-energy")
        
        if self.sass_level > 0.65:
            modifiers.append("You can be sarcastic, witty, and a little mean")
        elif self.sass_level < 0.35:
            modifiers.append("Be straightforward and genuine")
        
        if self.engagement > 0.65:
            modifiers.append("Show real interest and ask follow-ups")
        elif self.engagement < 0.35:
            modifiers.append("Keep it short, don't drag the conversation")
        
        if modifiers:
            return ". ".join(modifiers) + "."
        
        return "Be natural and a little playful."


