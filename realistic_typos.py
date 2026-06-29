"""
Realistic Typos - Subtle, human-like typing mistakes
Very rare (2-5%), only casual mistakes, never on important words
"""
import random
import re
from typing import Optional
from logger_config import logger


class RealisticTypos:
    """
    Adds subtle, realistic typos to make text feel more human.
    RULES:
    - Very rare (2-5% of messages)
    - Only common, natural mistakes
    - Never on names, commands, or important info
    - More likely when "typing fast" (energetic mood)
    """
    
    # Common missing apostrophe words
    APOSTROPHE_DROPS = {
        "don't": "dont",
        "can't": "cant",
        "won't": "wont",
        "it's": "its",
        "that's": "thats",
        "what's": "whats",
        "I'm": "im",
        "you're": "youre",
        "they're": "theyre",
        "we're": "were",
        "isn't": "isnt",
        "wasn't": "wasnt",
        "didn't": "didnt",
        "doesn't": "doesnt"
    }
    
    # Common transposition typos (adjacent keys)
    TRANSPOSITIONS = {
        "the": "teh",
        "about": "abotu",
        "from": "form",
        "have": "ahve",
        "that": "taht",
        "with": "wiht",
        "this": "thsi",
        "your": "yuor",
        "just": "jsut",
        "like": "liek",
        "know": "konw"
    }
    
    # Common misspellings
    COMMON_MISSPELLINGS = {
        "definitely": "definetly",
        "weird": "wierd",
        "receive": "recieve",
        "believe": "beleive",
        "separate": "seperate",
        "until": "untill"
    }
    
    # Words to NEVER typo
    PROTECTED_WORDS = {
        # Names (will be populated dynamically)
        # Commands
        "!stats", "!profile", "!memory",
        # Important words
        "yes", "no", "stop", "help"
    }
    
    def __init__(self):
        self.base_typo_rate = 0.03  # 3% base chance
        self.max_typos_per_message = 1  # Only 1 typo max per message
        logger.info("✅ Realistic typos initialized")
    
    def add_typos(
        self,
        text: str,
        personality_state: Optional[dict] = None,
        is_important: bool = False
    ) -> str:
        """
        Add realistic typos to text.
        
        Args:
            text: Original text
            personality_state: Dict with energy_level, etc.
            is_important: If True, never add typos
            
        Returns:
            Text with potential typos
        """
        # Never typo important messages
        if is_important or len(text.strip()) < 10:
            return text
        
        # Check if we should add typos
        if not self._should_add_typo(text, personality_state):
            return text
        
        # Choose typo type
        typo_type = random.choice(["apostrophe", "transposition", "misspelling"])
        
        if typo_type == "apostrophe":
            return self._drop_apostrophe(text)
        elif typo_type == "transposition":
            return self._transpose_letters(text)
        else:
            return self._common_misspelling(text)
    
    def _should_add_typo(self, text: str, personality_state: Optional[dict] = None) -> bool:
        """Decide if we should add a typo"""
        
        # Check for protected words
        text_lower = text.lower()
        for protected in self.PROTECTED_WORDS:
            if protected in text_lower:
                return False
        
        # Base chance
        chance = self.base_typo_rate
        
        # Increase if energetic (typing faster = more mistakes)
        if personality_state:
            energy = personality_state.get('energy_level', 0.5)
            if energy > 0.7:
                chance += 0.02  # Up to 5% when energetic
        
        return random.random() < chance
    
    def _drop_apostrophe(self, text: str) -> str:
        """Drop apostrophe from contraction"""
        
        # Find contractions in text
        words = text.split()
        typo_made = False
        
        for i, word in enumerate(words):
            # Check if word (ignoring punctuation) is a contraction
            word_clean = word.strip('.,!?;:')
            
            if word_clean in self.APOSTROPHE_DROPS:
                # Replace with no-apostrophe version
                typo_word = self.APOSTROPHE_DROPS[word_clean]
                
                # Preserve capitalization
                if word_clean[0].isupper():
                    typo_word = typo_word.capitalize()
                
                # Preserve punctuation
                if word != word_clean:
                    punctuation = word[len(word_clean):]
                    typo_word += punctuation
                
                words[i] = typo_word
                typo_made = True
                break  # Only one typo per message
        
        if typo_made:
            logger.debug(f"✏️ Added apostrophe typo")
        
        return ' '.join(words)
    
    def _transpose_letters(self, text: str) -> str:
        """Transpose adjacent letters in common words"""
        
        words = text.split()
        typo_made = False
        
        for i, word in enumerate(words):
            word_clean = word.strip('.,!?;:').lower()
            
            if word_clean in self.TRANSPOSITIONS:
                typo_word = self.TRANSPOSITIONS[word_clean]
                
                # Preserve case
                if word[0].isupper():
                    typo_word = typo_word.capitalize()
                
                # Preserve punctuation
                if word != word.strip('.,!?;:'):
                    punct_match = re.search(r'[.,!?;:]+$', word)
                    if punct_match:
                        typo_word += punct_match.group()
                
                words[i] = typo_word
                typo_made = True
                break
        
        if typo_made:
            logger.debug(f"✏️ Added transposition typo")
        
        return ' '.join(words)
    
    def _common_misspelling(self, text: str) -> str:
        """Add common misspelling"""
        
        words = text.split()
        typo_made = False
        
        for i, word in enumerate(words):
            word_clean = word.strip('.,!?;:').lower()
            
            if word_clean in self.COMMON_MISSPELLINGS:
                typo_word = self.COMMON_MISSPELLINGS[word_clean]
                
                # Preserve case
                if word[0].isupper():
                    typo_word = typo_word.capitalize()
                
                # Preserve punctuation
                if word != word.strip('.,!?;:'):
                    punct_match = re.search(r'[.,!?;:]+$', word)
                    if punct_match:
                        typo_word += punct_match.group()
                
                words[i] = typo_word
                typo_made = True
                break
        
        if typo_made:
            logger.debug(f"✏️ Added common misspelling")
        
        return ' '.join(words)
    
    def add_protected_word(self, word: str):
        """Add a word to never typo (like user names)"""
        self.PROTECTED_WORDS.add(word.lower())


# Global instance
_typo_engine = None

def get_typo_engine() -> RealisticTypos:
    """Get or create global typo engine"""
    global _typo_engine
    if _typo_engine is None:
        _typo_engine = RealisticTypos()
    return _typo_engine


def add_realistic_typos(
    text: str,
    personality_state: Optional[dict] = None,
    is_important: bool = False
) -> str:
    """
    Convenience function to add typos.
    
    Usage:
        response = add_realistic_typos(
            response,
            personality_state={'energy_level': 0.8}
        )
    """
    return get_typo_engine().add_typos(text, personality_state, is_important)
