"""
Correction Handler - Learning from User Corrections
Detects when users correct the bot and updates memories accordingly.
"""
import re
from typing import Optional, Dict, List
from datetime import datetime
from logger_config import logger


# CorrectionDetector removed (replaced by ThinkingManager)


class MemoryCorrector:
    """Updates memories based on corrections"""
    
    def __init__(self, memory_system):
        """
        Initialize memory corrector.
        
        Args:
            memory_system: UnifiedMemorySystem instance
        """
        self.memory = memory_system
    
    def apply_correction(
        self,
        correction: Dict,
        user_id: str,
        username: str,
        channel_id: str
    ):
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
            logger.warning("⚠️ No corrected statement found, skipping")
            return
        
        logger.info(f"🔧 Applying correction: '{original[:50]}...' → '{corrected[:50]}...'")
        
        # Find related memories (search for original statement)
        if original:
            related_memories = self.memory.search_memories(
                query=original,
                n_results=5
            )
            
            # Mark old memories as corrected
            if related_memories:
                logger.info(f"📝 Found {len(related_memories)} related memories to update")
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
        
        logger.info(f"✅ Correction stored in memory")
    
    def get_correction_history(
        self,
        user_id: str = None,
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


# Correction acknowledgments removed (replaced by LLM generation)
