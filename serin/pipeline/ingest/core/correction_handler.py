"""
Correction Handler - Learning from User Corrections
Detects when users correct the bot and updates memories accordingly.
"""
import re
from typing import Optional, Dict, List, Any
from datetime import datetime
from serin.state.logger import logger


class CorrectionDetector:
    """Detect when users are correcting the bot"""
    
    # Patterns that indicate corrections
    CORRECTION_PATTERNS: List[str] = [
        r"no[,\s]+(that's|thats|it's|its)?\s*(wrong|incorrect|not right|not true)",
        r"actually[,\s]+(it's|its|i|the)\s+",
        r"correction[:\s]+",
        r"wrong[,\s]+(it's|its)\s+",
        r"no[,\s]+i\s+meant\s+",
        r"that's\s+not\s+(right|correct|true|it)",
        r"not\s+(quite|exactly|really)",
        r"you\s+got\s+that\s+wrong",
        r"you're\s+wrong",
        r"that\s+was\s+wrong",
        r"fix\s+that",
        r"change\s+that\s+to",
    ]
    
    def detect_correction(
        self,
        message: str,
        previous_bot_response: str,
        context: Optional[List[Dict]] = None
    ) -> Optional[Dict]:
        """
        Detect if message is correcting the bot.
        
        Args:
            message: User's message
            previous_bot_response: Bot's last response
            context: Recent conversation context
        
        Returns:
            Dict with correction info, or None if not a correction
            {
                'is_correction': True,
                'original_statement': "...",
                'corrected_statement': "...",
                'confidence': 0.0-1.0
            }
        """
        message_lower = message.lower()
        
        # Check for correction patterns
        confidence = 0.0
        for pattern in self.CORRECTION_PATTERNS:
            if re.search(pattern, message_lower):
                confidence = 0.8
                break
        
        if confidence == 0:
            return None
        
        # Extract correction details
        correction = self._extract_correction_details(
            message,
            previous_bot_response,
            context
        )
        
        if correction:
            correction['confidence'] = confidence
            logger.info(f" Correction detected: {correction}")
            return correction
        
        return None
    
    def _extract_correction_details(
        self,
        message: str,
        bot_response: str,
        context: Optional[List[Dict]] = None
    ) -> Optional[Dict]:
        """
        Extract what's being corrected and the correct information.
        Uses simple pattern matching (no LLM needed for most cases).
        """
        message_lower = message.lower()
        
        # Pattern: "no, it's X" or "actually it's X"
        match = re.search(
            r"(?:no|actually|wrong)[,\s]+(?:it's|its|the|that's|thats)\s+(.+?)(?:\.|$)",
            message_lower,
            re.IGNORECASE
        )
        if match:
            corrected = match.group(1).strip()
            return {
                'is_correction': True,
                'original_statement': bot_response[:100],  # First part of bot response
                'corrected_statement': corrected,
                'correction_type': 'simple_replacement'
            }
        
        # Pattern: "not X, it's Y"
        match = re.search(
            r"not\s+(.+?)[,\s]+(?:it's|its|the)\s+(.+?)(?:\.|$)",
            message_lower,
            re.IGNORECASE
        )
        if match:
            incorrect = match.group(1).strip()
            correct = match.group(2).strip()
            return {
                'is_correction': True,
                'original_statement': incorrect,
                'corrected_statement': correct,
                'correction_type': 'explicit_correction'
            }
        
        # Pattern: "I meant X" (correcting user's own statement)
        match = re.search(
            r"i\s+meant\s+(.+?)(?:\.|$)",
            message_lower,
            re.IGNORECASE
        )
        if match:
            corrected = match.group(1).strip()
            # Look in context for what they originally said
            if context and len(context) > 1:
                original = context[-2].get('content', '')[:100]
            else:
                original = "previous statement"
            
            return {
                'is_correction': True,
                'original_statement': original,
                'corrected_statement': corrected,
                'correction_type': 'self_correction'
            }
        
        # Pattern: "change X to Y"
        match = re.search(
            r"change\s+(.+?)\s+to\s+(.+?)(?:\.|$)",
            message_lower,
            re.IGNORECASE
        )
        if match:
            old = match.group(1).strip()
            new = match.group(2).strip()
            return {
                'is_correction': True,
                'original_statement': old,
                'corrected_statement': new,
                'correction_type': 'explicit_change'
            }
        
        # Fallback: general correction detected but can't extract details
        return {
            'is_correction': True,
            'original_statement': bot_response[:100],
            'corrected_statement': message,
            'correction_type': 'general'
        }


class MemoryCorrector:
    """Updates memories based on corrections"""
    
    def __init__(self, memory_system: Any) -> None:
        """
        Initialize memory corrector.
        
        Args:
            memory_system: UnifiedMemorySystem instance
        """
        self.memory: Any = memory_system
    
    def apply_correction(
        self,
        correction: Dict,
        user_id: str,
        username: str,
        channel_id: str
    ) -> None:
        """
        Apply correction to memory system.
        
        Args:
            correction: Correction dict from CorrectionDetector
            user_id: User who made correction
            username: Username
            channel_id: Channel ID
        
        Process:
        1. Search for memories containing incorrect info
        2. Mark them as corrected/outdated
        3. Store new correct information with high importance
        """
        original = correction.get('original_statement', '')
        corrected = correction.get('corrected_statement', '')
        
        if not corrected:
            logger.warning(" No corrected statement found, skipping")
            return
        
        logger.info(f" Applying correction: '{original[:50]}...' → '{corrected[:50]}...'")
        
        # Find related memories (search for original statement)
        if original:
            related_memories = self.memory.search_memories(
                query=original,
                n_results=5
            )
            
            # Mark old memories as corrected
            if related_memories:
                logger.info(f" Found {len(related_memories)} related memories to update")
                # Note: ChromaDB doesn't support in-place updates easily
                # We'll just add the correction note in the new memory
        
        # Store correct information with high importance
        correction_note = f"{corrected} (corrected from: {original[:50]})"
        
        self.memory.add_memory(
            content=correction_note,
            user_id=user_id,
            username=username,
            channel_id=channel_id,
            participants=[user_id],
            emotional_tone='informative',
            importance=0.95,  # Very high - corrections are important!
            message_id=None
        )
        
        logger.info(f" Correction stored in memory")
    
    def get_correction_history(
        self,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get history of corrections.
        
        Args:
            user_id: Filter by user (optional)
            limit: Max corrections to return
        
        Returns:
            List of correction memories
        """
        # Search for memories containing "corrected from"
        corrections = self.memory.search_memories(
            query="corrected from",
            user_id=user_id,
            n_results=limit
        )
        
        return corrections


# Natural response templates for acknowledging corrections
CORRECTION_ACKNOWLEDGMENTS = [
    "oh my bad, {corrected}. got it",
    "ah right, {corrected}. thanks for correcting that",
    "oh yeah you're right, {corrected}",
    "my mistake, {corrected}",
    "oh whoops, {corrected}. noted",
    "gotcha, {corrected}",
    "ah okay, {corrected}. fixed",
    "oops yeah, {corrected}",
    "ah {corrected}, not {original}. got it",
    "oh right, {corrected}. my bad",
]


def get_correction_acknowledgment(correction: Dict) -> str:
    """
    Generate natural acknowledgment for correction.
    
    Args:
        correction: Correction dict
    
    Returns:
        Natural acknowledgment message
    """
    import random
    
    corrected = correction.get('corrected_statement', '').strip()
    original = correction.get('original_statement', '').strip()
    
    # Choose template
    template = random.choice(CORRECTION_ACKNOWLEDGMENTS)
    
    # Format with correction details
    try:
        if '{original}' in template:
            response = template.format(
                corrected=corrected[:50],
                original=original[:30]
            )
        else:
            response = template.format(corrected=corrected[:50])
        
        return response
    except (KeyError, IndexError, ValueError):
        # Fallback if formatting fails
        return f"oh my bad, {corrected}. got it"
