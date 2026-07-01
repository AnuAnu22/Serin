"""Conversational fillers and realistic typos — humanize bot responses."""

import re
import secrets

from serin.d1_3_state_core.logger import logger


def _rand() -> float:
    return secrets.randbelow(10_000_000) / 10_000_000


class ConversationalFillers:
    """
    Injects natural fillers into responses.
    Humans use fillers when thinking, being casual, or expressing uncertainty.
    """

    # Concession and agreement patterns — skip fillers on these
    CONCESSION_PATTERNS = [
        r"\byou'?re\s+right\b",
        r"\byou'?re\s+actually\s+right\b",
        r"\byou'?re\s+not\s+wrong\b",
        r"\bgood\s+point\b",
        r"\bfair\s+enough\b",
        r"\bi\s+was\s+wrong\b",
        r"\bi\s+stand\s+corrected\b",
        r"\bpoint\s+taken\b",
        r"\byou\s+make\s+a\s+good\s+point\b",
        r"\byou\s+got\s+me\b",
        r"\bi\s+concede\b",
        r"\bi\s+see\s+what\s+you\s+mean\b",
        r"\bactually\s+(?:yeah|true|fair)\b",
        r"\bokay\s+(?:yeah|fair)\b",
    ]

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
        personality_state: dict | None = None,
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

    def _is_concession(self, text: str) -> bool:
        """Check if the text contains a concession or agreement that should not be diluted."""
        return any(re.search(p, text.lower()) for p in self.CONCESSION_PATTERNS)

    def _should_add_fillers(self, text: str, personality_state: dict | None = None) -> bool:
        """Decide if fillers should be added"""

        # Skip fillers on concession sentences — don't dilute a clean agreement
        if self._is_concession(text):
            return False

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

        return _rand() < chance

    def _determine_filler_type(
        self,
        text: str,
        personality_state: dict | None = None,
        complexity: str = "simple"
    ) -> str:
        """
        Determine what type of filler to use based on context.
        """
        text_lower = text.lower()

        # Uncertainty fillers for questions or uncertain statements
        uncertainty_words = ["maybe", "might", "could", "possibly", "?"]
        if any(word in text_lower for word in uncertainty_words):
            if _rand() < 0.6:
                return "uncertainty"

        # Thinking fillers for complex responses
        if complexity == "complex" or len(text.split()) > 20:
            if _rand() < 0.4:
                return "thinking"

        # Emphasis fillers for strong statements
        strong_words = ["really", "very", "totally", "definitely", "absolutely"]
        if any(word in text_lower for word in strong_words):
            if _rand() < 0.3:
                return "emphasis"

        # Default: casual fillers
        return "casual"

    def _add_thinking_filler(self, text: str) -> str:
        """Add thinking filler at start"""
        filler = secrets.choice(self.THINKING_FILLERS)

        # Add with proper punctuation
        if filler in ["hold on", "let me think"]:
            return f"{filler}... {text}"
        else:
            return f"{filler}, {text}"

    def _add_casual_filler(self, text: str) -> str:
        """Add casual filler mid-sentence"""
        filler = secrets.choice(self.CASUAL_FILLERS)

        # Split into sentences
        sentences = re.split(r'([.!?])', text)

        if len(sentences) < 3:
            # Short text, add at start or middle
            words = text.split()
            if len(words) > 5:
                insert_pos = 3 + secrets.randbelow(min(8, len(words)) - 3 + 1)
                words.insert(insert_pos, filler)
                return ' '.join(words)
            return text

        # Add between sentences
        insert_pos = secrets.SystemRandom().randrange(1, len(sentences) - 1, 2)
        sentences.insert(insert_pos, f" {filler},")
        return ''.join(sentences)

    def _add_uncertainty_filler(self, text: str) -> str:
        """Add uncertainty filler at start"""
        filler = secrets.choice(self.UNCERTAINTY_FILLERS)

        # Make first letter lowercase if adding at start
        if text[0].isupper():
            text = text[0].lower() + text[1:]

        return f"{filler} {text}"

    def _add_emphasis_filler(self, text: str) -> str:
        """Add emphasis filler at start"""
        filler = secrets.choice(self.EMPHASIS_FILLERS)

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
    personality_state: dict | None = None,
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


# === Typos ===

"""
Realistic Typos - Subtle, human-like typing mistakes
Very rare (2-5%), only casual mistakes, never on important words
"""
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
        logger.info(" Realistic typos initialized")

    def add_typos(
        self,
        text: str,
        personality_state: dict | None = None,
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
        typo_type = secrets.choice(["apostrophe", "transposition", "misspelling"])

        if typo_type == "apostrophe":
            return self._drop_apostrophe(text)
        elif typo_type == "transposition":
            return self._transpose_letters(text)
        else:
            return self._common_misspelling(text)

    def _should_add_typo(self, text: str, personality_state: dict | None = None) -> bool:
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

        return _rand() < chance

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
            logger.debug("✏ Added apostrophe typo")

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
            logger.debug("✏ Added transposition typo")

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
            logger.debug("✏ Added common misspelling")

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
    personality_state: dict | None = None,
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
