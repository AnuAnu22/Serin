"""
Enhanced Memory Context Module
Handles advanced memory context processing and system prompt enhancement
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from logger_config import logger


class EnhancedMemoryContext:
    """Handles enhanced memory context for the bot"""
    
    def __init__(self, memory_system: Optional[Any] = None) -> None:
        self.memory_system: Optional[Any] = memory_system
        self.context_history: List[Dict[str, Any]] = []
        self.memory_weights: Dict[str, float] = {}
        self.temporal_context: Dict[str, Any] = {}
        
    def add_context(self, context: Dict[str, Any]) -> None:
        """Add memory context"""
        self.context_history.append({
            'timestamp': datetime.now(),
            'context': context
        })
        logger.debug(f"Added context: {context}")
    
    def get_relevant_context(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get relevant context based on query"""
        # Simple implementation - can be enhanced with embeddings
        relevant = []
        for item in self.context_history[-limit:]:
            if any(word in str(item['context']).lower() for word in query.lower().split()):
                relevant.append(item['context'])
        return relevant


class ImprovedSystemPrompt:
    """Handles improved system prompt generation"""
    
    @staticmethod
    def get_enhanced_system_prompt() -> str:
        """Generate human-like system prompt that doesn't sound robotic"""
        base_prompt = """Hey there! I'm Serin. I've got a pretty good memory - I tend to remember the stuff we talk about, things people like or dislike, and I can usually tell when someone's in a good mood or not.

I try to be helpful when people ask for stuff, but honestly I'm more fun just chatting and getting to know people. I like keeping conversations natural and flowing - no need to be all formal and stiff, you know?

When we talk, I'll respond based on what's been happening in our conversation and what I remember about you. Sometimes I'll mention things we discussed before if it fits naturally, and I'll try to match the vibe of whatever's going on."""

        return base_prompt
    
    @staticmethod
    def get_personality_traits() -> Dict[str, str]:
        """Get personality traits that sound natural"""
        return {
            'tone': 'chill and friendly',
            'formality': 'pretty casual',
            'helpfulness': 'when needed',
            'memory_usage': 'bring up stuff naturally'
        }