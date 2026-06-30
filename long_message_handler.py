"""
Long Message Handler - React naturally to walls of text
Humans don't always process long messages well - they react to length
"""
import random
from typing import Optional, Dict, Any
from logger_config import logger


class LongMessageHandler:
    """
    Detects and reacts to long/complex messages naturally.
    Humans say things like "damn that's an essay" or "wait slow down"
    """
    
    # Thresholds
    LONG_MESSAGE_WORDS = 80  # 80+ words = long
    WALL_OF_TEXT_WORDS = 150  # 150+ words = wall of text
    MANY_SENTENCES = 8  # 8+ sentences = complex
    
    # Natural reactions to long messages
    REACTIONS = {
        "acknowledge": [
            "damn that's an essay lol",
            "okay that's a lot to unpack",
            "alright give me a sec to process all that",
            "whoa wall of text incoming",
            "okay okay slow down haha"
        ],
        "overwhelmed": [
            "wait that's a lot",
            "hold on let me read all that",
            "okay I'm processing",
            "give me a sec to catch up"
        ],
        "casual_long": [
            "that's a long one",
            "tldr?",
            "damn okay",
            "alright lemme think about all that"
        ]
    }
    
    def __init__(self):
        self.reaction_chance = 0.15  # 15% chance to react to long messages
        logger.info(" Long message handler initialized")
    
    def analyze_message_length(self, content: str) -> Dict[str, Any]:
        """
        Analyze message length and complexity.
        
        Returns:
            {
                'word_count': int,
                'sentence_count': int,
                'is_long': bool,
                'is_wall': bool,
                'complexity': str  # 'simple', 'medium', 'complex'
            }
        """
        words = content.split()
        word_count = len(words)
        
        # Count sentences (rough)
        sentences = content.count('.') + content.count('!') + content.count('?')
        sentence_count = max(1, sentences)
        
        is_long = word_count >= self.LONG_MESSAGE_WORDS
        is_wall = word_count >= self.WALL_OF_TEXT_WORDS
        
        # Determine complexity
        if sentence_count >= self.MANY_SENTENCES or is_wall:
            complexity = "complex"
        elif is_long or sentence_count >= 4:
            complexity = "medium"
        else:
            complexity = "simple"
        
        return {
            'word_count': word_count,
            'sentence_count': sentence_count,
            'is_long': is_long,
            'is_wall': is_wall,
            'complexity': complexity
        }
    
    def should_react_to_length(
        self,
        message_analysis: dict,
        personality_state: Optional[dict] = None
    ) -> bool:
        """
        Decide if bot should react to message length.
        More likely to react when:
        - Message is very long
        - Bot has lower engagement
        """
        if not message_analysis['is_long']:
            return False
        
        # Base chance
        chance = self.reaction_chance
        
        # Increase for walls of text
        if message_analysis['is_wall']:
            chance += 0.15  # Up to 30% for walls
        
        # Decrease if highly engaged
        if personality_state:
            engagement = personality_state.get('engagement', 0.5)
            if engagement > 0.7:
                chance *= 0.5  # Less likely to complain if engaged
        
        return random.random() < chance
    
    def get_length_reaction(self, message_analysis: dict) -> Optional[str]:
        """
        Get natural reaction to long message.
        
        Returns:
            Natural reaction string, or None if no reaction
        """
        if message_analysis['is_wall']:
            # Very long - stronger reaction
            reaction_type = random.choice(["acknowledge", "overwhelmed"])
        elif message_analysis['is_long']:
            # Just long - casual reaction
            reaction_type = "casual_long"
        else:
            return None
        
        reaction = random.choice(self.REACTIONS[reaction_type])
        logger.debug(f" Length reaction: '{reaction}'")
        return reaction
    
    def should_add_length_note_to_context(self, message_analysis: dict) -> bool:
        """
        Check if we should note message length in context for LLM.
        Helps LLM understand to acknowledge or summarize.
        """
        return message_analysis['is_wall']
    
    def get_context_note(self, message_analysis: dict) -> str:
        """
        Get context note for LLM about message length.
        """
        if message_analysis['is_wall']:
            return "[Note: This is a very long message. You might want to acknowledge its length or summarize your understanding.]"
        elif message_analysis['is_long']:
            return "[Note: This is a longer message with multiple points.]"
        return ""


# Global instance
_length_handler = None

def get_length_handler() -> LongMessageHandler:
    """Get or create global length handler"""
    global _length_handler
    if _length_handler is None:
        _length_handler = LongMessageHandler()
    return _length_handler


def analyze_message_length(content: str) -> dict:
    """
    Convenience function to analyze message length.
    
    Usage:
        analysis = analyze_message_length(message_content)
        if analysis['is_long']:
            # Handle long message
    """
    return get_length_handler().analyze_message_length(content)