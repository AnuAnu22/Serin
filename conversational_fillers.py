"""
Conversational Fillers - Natural speech patterns
Adds "hmm", "like", "you know" etc. to make responses feel more human
"""
import random
import re
from typing import Optional
from logger_config import logger


class ConversationalFillers:
    """
    Injects natural fillers into responses.
    Humans use fillers when thinking, being casual, or expressing uncertainty.
    """
    
    # Filler categories
    THINKING_FILLERS = [
        "hmm", "uh", "um", "well", "let me think", "hold on"
    ]
    
    CASUAL_FILLERS = [
        "like", "you know", "I mean", "kinda", "sorta", "basically"
    ]
    
    UNCERTAINTY_FILLERS = [
        "I think", "maybe", "probably", "I guess", "not sure but"
    ]
    
    EMPHASIS_FILLERS = [
        "honestly", "tbh", "ngl", "fr", "literally"
    ]
    
    def __init__(self):
        self.injection_rate = 0.08  # 8% base chance per message
        logger.info(" Conversational fillers initialized")
    
    def add_fillers(
        self,
        text: str,
        personality_state: Optional[dict] = None,
        message_complexity: str = "simple"
    ) -> str:
        """
        Add natural fillers to text based on context.
        
        Args:
            text: Original response text
            personality_state: Dict with energy, sass, engagement levels
            message_complexity: "simple", "medium", "complex"
            
        Returns:
            Text with natural fillers added
        """
        if not text or len(text) < 10:
            return text
        
        # Check if we should add fillers
        if not self._should_add_fillers(text, personality_state):
            return text
        
        # Determine filler type based on context
        filler_type = self._determine_filler_type(
            text, personality_state, message_complexity
        )
        
        if filler_type == "thinking":
            return self._add_thinking_filler(text)
        elif filler_type == "casual":
            return self._add_casual_filler(text)
        elif filler_type == "uncertainty":
            return self._add_uncertainty_filler(text)
        elif filler_type == "emphasis":
            return self._add_emphasis_filler(text)
        
        return text
    
    def _should_add_fillers(self, text: str, personality_state: Optional[dict] = None) -> bool:
        """Decide if fillers should be added"""
        
        # Don't add to very short messages
        if len(text.split()) < 5:
            return False
        
        # Don't add if already has common fillers
        existing_fillers = ["hmm", "uh", "like", "you know", "I mean", "tbh"]
        if any(filler in text.lower() for filler in existing_fillers):
            return False
        
        # Base chance
        chance = self.injection_rate
        
        # Increase chance if energetic (more casual)
        if personality_state:
            energy = personality_state.get('energy_level', 0.5)
            if energy > 0.7:
                chance += 0.05
        
        return random.random() < chance
    
    def _determine_filler_type(
        self,
        text: str,
        personality_state: Optional[dict] = None,
        complexity: str = "simple"
    ) -> str:
        """
        Determine what type of filler to use based on context.
        """
        text_lower = text.lower()
        
        # Uncertainty fillers for questions or uncertain statements
        uncertainty_words = ["maybe", "might", "could", "possibly", "?"]
        if any(word in text_lower for word in uncertainty_words):
            if random.random() < 0.6:
                return "uncertainty"
        
        # Thinking fillers for complex responses
        if complexity == "complex" or len(text.split()) > 20:
            if random.random() < 0.4:
                return "thinking"
        
        # Emphasis fillers for strong statements
        strong_words = ["really", "very", "totally", "definitely", "absolutely"]
        if any(word in text_lower for word in strong_words):
            if random.random() < 0.3:
                return "emphasis"
        
        # Default: casual fillers
        return "casual"
    
    def _add_thinking_filler(self, text: str) -> str:
        """Add thinking filler at start"""
        filler = random.choice(self.THINKING_FILLERS)
        
        # Add with proper punctuation
        if filler in ["hold on", "let me think"]:
            return f"{filler}... {text}"
        else:
            return f"{filler}, {text}"
    
    def _add_casual_filler(self, text: str) -> str:
        """Add casual filler mid-sentence"""
        filler = random.choice(self.CASUAL_FILLERS)
        
        # Split into sentences
        sentences = re.split(r'([.!?])', text)
        
        if len(sentences) < 3:
            # Short text, add at start or middle
            words = text.split()
            if len(words) > 5:
                insert_pos = random.randint(3, min(8, len(words)))
                words.insert(insert_pos, filler)
                return ' '.join(words)
            return text
        
        # Add between sentences
        insert_pos = random.randrange(1, len(sentences) - 1, 2)
        sentences.insert(insert_pos, f" {filler},")
        return ''.join(sentences)
    
    def _add_uncertainty_filler(self, text: str) -> str:
        """Add uncertainty filler at start"""
        filler = random.choice(self.UNCERTAINTY_FILLERS)
        
        # Make first letter lowercase if adding at start
        if text[0].isupper():
            text = text[0].lower() + text[1:]
        
        return f"{filler} {text}"
    
    def _add_emphasis_filler(self, text: str) -> str:
        """Add emphasis filler at start"""
        filler = random.choice(self.EMPHASIS_FILLERS)
        
        # Add naturally
        if filler in ["honestly", "literally"]:
            return f"{filler}, {text}"
        else:
            return f"{filler} {text}"


# Global instance
_filler_engine = None

def get_filler_engine() -> ConversationalFillers:
    """Get or create global filler engine"""
    global _filler_engine
    if _filler_engine is None:
        _filler_engine = ConversationalFillers()
    return _filler_engine


def add_conversational_fillers(
    text: str,
    personality_state: Optional[dict] = None,
    complexity: str = "simple"
) -> str:
    """
    Convenience function to add fillers.
    
    Usage:
        response = add_conversational_fillers(
            response,
            personality_state={'energy_level': 0.8},
            complexity='medium'
        )
    """
    return get_filler_engine().add_fillers(text, personality_state, complexity)
