"""
Conversation Analyzer - Multi-Message Reasoning
Analyzes conversation flow instead of individual messages.
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from logger_config import logger


class ConversationAnalyzer:
    def __init__(self):
        """Initialize conversation analyzer"""
        self.active_topics = {}  # channel_id -> current topic
        self.topic_history = {}  # channel_id -> list of past topics
        
    def analyze_conversation_flow(
        self,
        messages: List[Dict],
        channel_id: str
    ) -> Dict:
        """
        Analyze the flow of last N messages as a unit.
        
        Args:
            messages: List of recent messages with 'content', 'user_name', 'timestamp'
            channel_id: Channel ID
        
        Returns:
            Dict with conversation analysis
        """
        if not messages:
            return self._empty_analysis()
        
        try:
            # Detect current topic
            current_topic = self._detect_topic(messages)
            
            # Check for topic transitions
            previous_topic = self.active_topics.get(channel_id)
            topic_changed = previous_topic and previous_topic != current_topic
            
            # Update topic tracking
            if current_topic:
                self.active_topics[channel_id] = current_topic
                
                if channel_id not in self.topic_history:
                    self.topic_history[channel_id] = []
                
                if topic_changed:
                    self.topic_history[channel_id].append({
                        'topic': previous_topic,
                        'ended_at': datetime.now()
                    })
            
            # Detect conversation patterns
            patterns = self._detect_patterns(messages)
            
            # Analyze participants
            participants = self._analyze_participants(messages)
            
            # Determine conversation type
            conv_type = self._classify_conversation(messages, patterns)
            
            result = {
                'current_topic': current_topic,
                'previous_topic': previous_topic,
                'topic_changed': topic_changed,
                'patterns': patterns,
                'participants': participants,
                'conversation_type': conv_type,
                'summary': self._generate_summary(messages, current_topic)
            }
            
            logger.debug(f"📊 Conversation analysis: topic='{current_topic}', type={conv_type}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error analyzing conversation: {e}")
            return self._empty_analysis()
    
    def _detect_topic(self, messages: List[Dict]) -> Optional[str]:
        """
        Detect main topic from messages.
        Uses keyword frequency and noun extraction (simple).
        """
        if not messages:
            return None
        
        # Combine all message content
        combined_text = ' '.join(msg['content'].lower() for msg in messages[-5:])
        
        # Extract potential topic keywords (nouns, capitalized words)
        words = combined_text.split()
        
        # Simple topic detection: most common significant words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were',
                    'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'about', 'what',
                    'this', 'that', 'it', 'you', 'i', 'we', 'they', 'he', 'she', 'do'}
        
        word_freq = {}
        for word in words:
            clean_word = word.strip('.,!?')
            if len(clean_word) > 3 and clean_word not in stopwords:
                word_freq[clean_word] = word_freq.get(clean_word, 0) + 1
        
        if word_freq:
            # Get most common word as topic
            topic = max(word_freq, key=word_freq.get)
            return topic
        
        return None
    
    def _detect_patterns(self, messages: List[Dict]) -> Dict:
        """Detect conversation patterns"""
        if len(messages) < 2:
            return {}
        
        patterns = {
            'is_back_and_forth': self._is_back_and_forth(messages),
            'is_group_discussion': self._is_group_discussion(messages),
            'has_questions': any('?' in msg['content'] for msg in messages),
            'has_exclamations': sum(msg['content'].count('!') for msg in messages) > 2,
            'avg_message_length': sum(len(msg['content']) for msg in messages) / len(messages)
        }
        
        return patterns
    
    def _is_back_and_forth(self, messages: List[Dict]) -> bool:
        """Check if conversation is back-and-forth between 2 people"""
        if len(messages) < 3:
            return False
        
        users = [msg.get('user_id') or msg.get('user_name') for msg in messages]
        unique_users = set(users)
        
        return len(unique_users) == 2 and len(messages) >= 3
    
    def _is_group_discussion(self, messages: List[Dict]) -> bool:
        """Check if conversation involves 3+ people"""
        users = set(msg.get('user_id') or msg.get('user_name') for msg in messages)
        return len(users) >= 3
    
    def _analyze_participants(self, messages: List[Dict]) -> Dict:
        """Analyze participant involvement"""
        participant_msgs = {}
        
        for msg in messages:
            user = msg.get('user_id') or msg.get('user_name', 'Unknown')
            participant_msgs[user] = participant_msgs.get(user, 0) + 1
        
        return {
            'count': len(participant_msgs),
            'message_distribution': participant_msgs,
            'most_active': max(participant_msgs, key=participant_msgs.get) if participant_msgs else None
        }
    
    def _classify_conversation(self, messages: List[Dict], patterns: Dict) -> str:
        """Classify type of conversation"""
        if patterns.get('has_questions'):
            return 'question_answer'
        elif patterns.get('is_back_and_forth'):
            return 'dialogue'
        elif patterns.get('is_group_discussion'):
            return 'group_discussion'
        elif patterns.get('avg_message_length', 0) > 100:
            return 'storytelling'
        else:
            return 'casual_chat'
    
    def _generate_summary(self, messages: List[Dict], topic: Optional[str]) -> str:
        """Generate brief conversation summary"""
        if not messages:
            return "No conversation"
        
        participants = set(msg.get('user_name', 'Unknown') for msg in messages)
        participant_names = ', '.join(list(participants)[:3])
        
        if topic:
            return f"{participant_names} discussing {topic}"
        else:
            return f"{participant_names} chatting"
    
    def _empty_analysis(self) -> Dict:
        """Return empty analysis structure"""
        return {
            'current_topic': None,
            'previous_topic': None,
            'topic_changed': False,
            'patterns': {},
            'participants': {'count': 0},
            'conversation_type': 'unknown',
            'summary': 'No analysis available'
        }
    
    def get_topic_history(self, channel_id: str, limit: int = 5) -> List[Dict]:
        """Get recent topic history for a channel"""
        return self.topic_history.get(channel_id, [])[-limit:]
    
    def should_acknowledge_topic_change(
        self,
        channel_id: str,
        time_since_last_response: float
    ) -> bool:
        """
        Decide if bot should acknowledge topic change.
        
        Args:
            channel_id: Channel ID
            time_since_last_response: Seconds since last bot response
        
        Returns:
            True if should acknowledge the topic shift
        """
        # If topic changed recently and bot hasn't responded in a while
        if channel_id in self.active_topics:
            previous = self.topic_history.get(channel_id, [])
            if previous and time_since_last_response > 300:  # 5 minutes
                return True
        
        return False
