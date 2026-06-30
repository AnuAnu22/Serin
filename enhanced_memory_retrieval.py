"""
Enhanced Memory Retrieval System for Human-like Behavior
Improves memory selection, relevance scoring, and personality consistency
"""

import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict, Counter
from logger_config import logger
import sqlite3

from dataclasses import dataclass

@dataclass
class HumanLikeMemoryQuery:
    """Enhanced query structure for human-like memory retrieval"""
    query: str
    user_id: str
    conversation_context: Optional[List[Dict]] = None
    emotional_state: str = "neutral"
    conversation_phase: str = "casual"  # casual, focused, emotional
    personality_mood: str = "friendly"
    temporal_priority: str = "recent"  # recent, important, relevant

class PersonalityConsistencyAnalyzer:
    """Analyzes and maintains personality consistency in memory retrieval"""
    
    def __init__(self, memory_system: Any) -> None:
        self.memory: Any = memory_system
        self.personality_weights: Dict[str, float] = {}
        self.conversation_history: Dict[str, List[Dict]] = {}
        
    def analyze_user_personality(self, user_id: str) -> Dict:
        """Analyze user's personality traits and communication style"""
        try:
            # Get user profile
            profile = self.memory.get_user_profile(user_id)
            if not profile:
                return {"traits": [], "interests": [], "communication_style": "neutral"}
            
            # Get user's recent memories for style analysis
            recent_memories = self.memory.search_memories(
                query="conversation style communication",
                user_id=user_id,
                n_results=20
            )
            
            # Analyze communication patterns
            communication_patterns = []
            for memory in recent_memories:
                content = memory.get('content', '').lower()
                # Simple pattern analysis - could be enhanced with NLP
                if any(word in content for word in ['excited', 'happy', 'great', 'awesome']):
                    communication_patterns.append('positive')
                if any(word in content for word in ['sad', 'worried', 'concerned', 'upset']):
                    communication_patterns.append('concerned')
                if any(word in content for word in ['analysis', 'research', 'data', 'study']):
                    communication_patterns.append('analytical')
            
            return {
                "declared_traits": profile.get('personality_traits', []),
                "declared_interests": profile.get('interests', []),
                "communication_style": profile.get('communication_style', 'neutral'),
                "recent_patterns": list(set(communication_patterns)),
                "conversation_count": len(recent_memories)
            }
            
        except Exception as e:
            logger.error(f" Personality analysis failed: {e}")
            return {"traits": [], "interests": [], "communication_style": "neutral"}

class HumanLikeMemoryRetriever:
    """Enhanced memory retrieval system designed for human-like behavior"""
    
    def __init__(self, memory_system: Any) -> None:
        self.memory: Any = memory_system
        self.personality_analyzer: PersonalityConsistencyAnalyzer = PersonalityConsistencyAnalyzer(memory_system)
        self.retrieval_history: Dict[str, List[Dict]] = {}
        self.human_behavior_weights: Dict[str, float] = {
            "relevance": 0.35,
            "recency": 0.25,
            "importance": 0.15,
            "personality_match": 0.15,
            "emotional_resonance": 0.10
        }
        
    def search_memories_human_like(self, query: HumanLikeMemoryQuery) -> List[Dict]:
        """
        Enhanced memory search optimized for human-like behavior patterns
        """
        logger.debug(f" Human-like memory search for user {query.user_id}: {query.query[:50]}...")
        
        try:
            # Analyze user's personality for this search
            user_personality = self.personality_analyzer.analyze_user_personality(query.user_id)
            
            # Get initial memory candidates using hybrid approach
            candidates = self._get_memory_candidates(query)
            
            # Apply human-like relevance scoring
            scored_memories = self._apply_human_like_scoring(
                candidates, query, user_personality
            )
            
            # Apply conversation-aware filtering
            filtered_memories = self._filter_conversation_aware_memories(
                scored_memories, query
            )
            
            # Apply personality consistency checks
            personality_filtered = self._apply_personality_consistency(
                filtered_memories, query, user_personality
            )
            
            # Sort by human-like priority
            final_memories = self._sort_by_human_like_priority(
                personality_filtered, query
            )
            
            logger.info(f" Human-like search: {len(final_memories)} memories selected")
            return final_memories
            
        except Exception as e:
            logger.error(f" Human-like memory search failed: {e}")
            return []
    
    def _get_memory_candidates(self, query: HumanLikeMemoryQuery) -> List[Dict]:
        """Get memory candidates using multiple strategies"""
        candidates = []
        
        # Strategy 1: Direct semantic search
        direct_results = self.memory.search_memories(
            query=query.query,
            user_id=query.user_id,
            n_results=15
        )
        candidates.extend(direct_results)
        
        # Strategy 2: Context-enhanced search
        if query.conversation_context:
            context_query = self._build_context_query(query.conversation_context, query.query)
            context_results = self.memory.search_memories(
                query=context_query,
                user_id=query.user_id,
                n_results=10
            )
            candidates.extend(context_results)
        
        # Strategy 3: Temporal-aware search
        temporal_candidates = self._get_temporal_candidates(query)
        candidates.extend(temporal_candidates)
        
        # Remove duplicates based on memory ID
        seen_ids = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate not in seen_ids:
                unique_candidates.append(candidate)
                seen_ids.add(id(candidate))
        
        return unique_candidates[:20]  # Limit to top 20 candidates
    
    def _build_context_query(self, conversation_context: List[Dict], original_query: str) -> str:
        """Build enhanced query using conversation context"""
        context_terms = []
        
        # Add recent conversation topics
        for msg in conversation_context[-5:]:
            content = msg.get('content', '').lower()
            # Extract key terms (simple approach - could be enhanced with NLP)
            words = content.split()
            key_terms = [w for w in words if len(w) > 3 and w not in ['that', 'this', 'with', 'they', 'them', 'were']]
            context_terms.extend(key_terms[:3])  # Top 3 terms per message
        
        # Combine with original query
        all_terms = [original_query] + context_terms
        return " ".join(all_terms[:8])  # Limit to 8 terms total
    
    def _get_temporal_candidates(self, query: HumanLikeMemoryQuery) -> List[Dict]:
        """Get temporally relevant memory candidates"""
        try:
            # Get memories from different time periods
            now = datetime.now()
            time_periods = [
                ("today", now - timedelta(days=1)),
                ("this_week", now - timedelta(days=7)),
                ("this_month", now - timedelta(days=30))
            ]
            
            temporal_candidates = []
            for period_name, cutoff_date in time_periods:
                # Get memories from this period
                period_results = self.memory.search_memories(
                    query=query.query,
                    user_id=query.user_id,
                    n_results=5
                )
                
                # Filter by time period - handle both string and datetime timestamps
                def safe_datetime_convert(timestamp):
                    """Safely convert timestamp to datetime, handling both string and datetime inputs"""
                    if isinstance(timestamp, str):
                        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    return timestamp
                
                period_filtered = [
                    mem for mem in period_results
                    if safe_datetime_convert(mem['timestamp']) >= cutoff_date
                ]
                
                temporal_candidates.extend(period_filtered)
            
            return temporal_candidates
            
        except Exception as e:
            logger.error(f" Temporal candidate search failed: {e}")
            return []
    
    def _apply_human_like_scoring(
        self, 
        candidates: List[Dict], 
        query: HumanLikeMemoryQuery,
        user_personality: Dict
    ) -> List[Dict]:
        """Apply human-like relevance scoring algorithm"""
        scored_memories = []
        
        for memory in candidates:
            # Base relevance score (existing ChromaDB score)
            base_relevance = memory.get('relevance', 0.5)
            
            # Recency score (human-like temporal importance)
            recency_score = self._calculate_human_recency(memory)
            
            # Importance score (human-like priority)
            importance_score = memory.get('importance', 0.5)
            
            # Personality match score
            personality_match = self._calculate_personality_match(
                memory, user_personality, query.personality_mood
            )
            
            # Emotional resonance score
            emotional_resonance = self._calculate_emotional_resonance(
                memory, query.emotional_state
            )
            
            # Combined human-like score
            human_score = (
                base_relevance * self.human_behavior_weights["relevance"] +
                recency_score * self.human_behavior_weights["recency"] +
                importance_score * self.human_behavior_weights["importance"] +
                personality_match * self.human_behavior_weights["personality_match"] +
                emotional_resonance * self.human_behavior_weights["emotional_resonance"]
            )
            
            memory['human_relevance'] = round(human_score, 4)
            memory['score_breakdown'] = {
                'base_relevance': base_relevance,
                'recency': recency_score,
                'importance': importance_score,
                'personality_match': personality_match,
                'emotional_resonance': emotional_resonance
            }
            
            scored_memories.append(memory)
        
        return scored_memories
    
    def _calculate_human_recency(self, memory: Dict) -> float:
        """Calculate human-like recency score (more nuanced than linear decay)"""
        try:
            # Handle both string and datetime timestamps
            def safe_datetime_convert(timestamp):
                if isinstance(timestamp, str):
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return timestamp
            
            timestamp = safe_datetime_convert(memory['timestamp'])
            now = datetime.now()
            age_days = (now - timestamp).days
            
            # Human-like recency curve - more weight for very recent, gradual decline
            if age_days == 0:
                return 1.0  # Today
            elif age_days < 7:
                return 0.9 - (age_days * 0.05)  # Recent week
            elif age_days < 30:
                return 0.7 - ((age_days - 7) * 0.01)  # Recent month
            elif age_days < 90:
                return 0.5 - ((age_days - 30) * 0.005)  # Recent quarter
            else:
                return max(0.1, 0.3 - ((age_days - 90) * 0.001))  # Older memories
                
        except Exception:
            return 0.5  # Default score for invalid timestamps
    
    def _calculate_personality_match(
        self, 
        memory: Dict, 
        user_personality: Dict, 
        mood: str
    ) -> float:
        """Calculate personality consistency score"""
        try:
            content = memory.get('content', '').lower()
            declared_traits = user_personality.get('declared_traits', [])
            declared_interests = user_personality.get('declared_interests', [])
            communication_style = user_personality.get('communication_style', 'neutral')
            
            # Check trait mentions
            trait_matches = sum(1 for trait in declared_traits if trait.lower() in content)
            trait_score = min(1.0, trait_matches / max(1, len(declared_traits)))
            
            # Check interest mentions
            interest_matches = sum(1 for interest in declared_interests if interest.lower() in content)
            interest_score = min(1.0, interest_matches / max(1, len(declared_interests)))
            
            # Mood consistency check
            mood_keywords = {
                'friendly': ['nice', 'good', 'great', 'awesome', 'cool'],
                'analytical': ['data', 'analysis', 'study', 'research', 'explain'],
                'empathetic': ['understand', 'feel', 'sorry', 'help', 'support']
            }
            
            mood_matches = sum(1 for word in mood_keywords.get(mood, []) if word in content)
            mood_score = min(1.0, mood_matches / max(1, len(mood_keywords.get(mood, []))))
            
            # Weighted combination
            personality_match = (trait_score * 0.4 + interest_score * 0.4 + mood_score * 0.2)
            
            return round(personality_match, 3)
            
        except Exception:
            return 0.5  # Default neutral score
    
    def _calculate_emotional_resonance(self, memory: Dict, target_emotion: str) -> float:
        """Calculate emotional resonance score"""
        try:
            content = memory.get('content', '').lower()
            memory_emotion = memory.get('emotional_tone', 'neutral')
            
            # Emotion matching matrix
            emotion_compatibility = {
                'friendly': {'happy': 1.0, 'excited': 0.9, 'neutral': 0.7, 'sad': 0.3, 'angry': 0.1},
                'empathetic': {'sad': 1.0, 'worried': 0.8, 'neutral': 0.6, 'happy': 0.4, 'angry': 0.2},
                'analytical': {'neutral': 1.0, 'curious': 0.8, 'excited': 0.6, 'sad': 0.3, 'angry': 0.2},
                'excited': {'excited': 1.0, 'happy': 0.9, 'curious': 0.7, 'neutral': 0.5, 'sad': 0.2},
                'calm': {'neutral': 1.0, 'happy': 0.8, 'sad': 0.6, 'excited': 0.4, 'angry': 0.2}
            }
            
            target_compatibility = emotion_compatibility.get(target_emotion, {})
            resonance_score = target_compatibility.get(memory_emotion, 0.5)
            
            return round(resonance_score, 3)
            
        except Exception:
            return 0.5  # Default neutral score
    
    def _filter_conversation_aware_memories(
        self, 
        candidates: List[Dict], 
        query: HumanLikeMemoryQuery
    ) -> List[Dict]:
        """Filter memories based on conversation awareness"""
        if not query.conversation_context:
            return candidates
        
        # Get recent conversation topics for filtering
        recent_topics = set()
        for msg in query.conversation_context[-5:]:
            content = msg.get('content', '').lower()
            words = content.split()
            # Simple topic extraction
            topics = [w for w in words if len(w) > 4 and w not in ['that', 'this', 'with', 'they']]
            recent_topics.update(topics[:2])  # Top 2 per message
        
        # Filter candidates based on topic relevance
        conversation_aware = []
        for memory in candidates:
            content = memory.get('content', '').lower()
            topic_relevance = sum(1 for topic in recent_topics if topic in content)
            
            # Prioritize memories that relate to recent conversation
            if topic_relevance > 0:
                memory['conversation_relevance'] = topic_relevance / max(1, len(recent_topics))
                conversation_aware.append(memory)
            elif len(conversation_aware) < len(candidates) * 0.3:  # Keep some non-topical memories
                memory['conversation_relevance'] = 0
                conversation_aware.append(memory)
        
        return conversation_aware
    
    def _apply_personality_consistency(
        self, 
        candidates: List[Dict], 
        query: HumanLikeMemoryQuery,
        user_personality: Dict
    ) -> List[Dict]:
        """Apply personality consistency validation"""
        consistent_memories = []
        
        for memory in candidates:
            # Check if memory content contradicts user's personality
            content = memory.get('content', '').lower()
            declared_traits = [t.lower() for t in user_personality.get('declared_traits', [])]
            
            # Simple consistency detection
            consistency_score = 0
            for trait in declared_traits:
                if trait in content:
                    # If trait is mentioned, it's likely consistent with user's personality
                    consistency_score += 1
            
            # Apply personality consistency bonus
            personality_consistency_bonus = min(0.2, consistency_score * 0.05)
            memory['personality_consistency'] = personality_consistency_bonus
            
            # Only exclude memories with no personality consistency at all
            if consistency_score <= 0 and declared_traits:
                continue
            
            consistent_memories.append(memory)
        
        return consistent_memories
    
    def _sort_by_human_like_priority(
        self, 
        candidates: List[Dict], 
        query: HumanLikeMemoryQuery
    ) -> List[Dict]:
        """Sort memories by human-like priority rules"""
        
        def human_priority_score(memory):
            """Calculate human-like priority score"""
            scores = [
                memory.get('human_relevance', 0) * 0.4,
                memory.get('conversation_relevance', 0) * 0.3,
                memory.get('personality_consistency', 0) * 0.2,
                1.0 / max(1, memory.get('age_days', 1)) * 0.1  # Recency bonus
            ]
            return sum(scores)
        
        # Sort by priority score
        sorted_memories = sorted(candidates, key=human_priority_score, reverse=True)
        
        # Apply conversation phase adjustments
        if query.conversation_phase == "focused":
            # Prioritize informational memories
            focused_memories = [
                mem for mem in sorted_memories 
                if any(word in mem.get('content', '').lower() 
                      for word in ['information', 'fact', 'detail', 'explain'])
            ]
            remaining_memories = [mem for mem in sorted_memories if mem not in focused_memories]
            sorted_memories = focused_memories + remaining_memories
        
        elif query.conversation_phase == "emotional":
            # Prioritize emotionally relevant memories
            emotional_memories = [
                mem for mem in sorted_memories 
                if mem.get('emotional_tone', 'neutral') != 'neutral'
            ]
            remaining_memories = [mem for mem in sorted_memories if mem not in emotional_memories]
            sorted_memories = emotional_memories + remaining_memories
        
        return sorted_memories[:10]  # Return top 10

class MemoryQualityAssessor:
    """Assesses and maintains memory quality for human-like conversations"""
    
    def __init__(self, memory_system: Any) -> None:
        self.memory: Any = memory_system
        self.quality_thresholds: Dict[str, float] = {
            'excellent': 0.8,
            'good': 0.6,
            'acceptable': 0.4,
            'poor': 0.2
        }
    
    def assess_memory_quality(self, memory_content: str, metadata: Dict) -> Dict:
        """Assess the quality of a memory for human-like conversations"""
        try:
            quality_factors = {
                'content_clarity': self._assess_content_clarity(memory_content),
                'information_density': self._assess_information_density(memory_content),
                'emotional_context': self._assess_emotional_context(metadata),
                'personal_relevance': self._assess_personal_relevance(metadata),
                'temporal_relevance': self._assess_temporal_relevance(metadata)
            }
            
            # Calculate overall quality score
            weights = {
                'content_clarity': 0.25,
                'information_density': 0.20,
                'emotional_context': 0.20,
                'personal_relevance': 0.20,
                'temporal_relevance': 0.15
            }
            
            overall_quality = sum(
                quality_factors[factor] * weights[factor] 
                for factor in quality_factors
            )
            
            # Determine quality category
            quality_category = self._categorize_quality(overall_quality)
            
            return {
                'overall_quality': round(overall_quality, 3),
                'quality_category': quality_category,
                'quality_factors': quality_factors,
                'improvement_suggestions': self._generate_quality_suggestions(quality_factors)
            }
            
        except Exception as e:
            logger.error(f" Memory quality assessment failed: {e}")
            return {'overall_quality': 0.5, 'quality_category': 'acceptable', 'error': str(e)}
    
    def _assess_content_clarity(self, content: str) -> float:
        """Assess content clarity for human understanding"""
        try:
            # Simple clarity metrics
            words = content.split()
            if len(words) < 3:
                return 0.1  # Too short
            if len(words) > 100:
                return 0.8  # Long but might be detailed
            
            # Check for clear structure
            has_sentences = content.count('.') > 0 or content.count('!') > 0 or content.count('?') > 0
            has_proper_casing = any(word[0].isupper() for word in words if len(word) > 1)
            
            clarity_score = 0.5
            if has_sentences:
                clarity_score += 0.3
            if has_proper_casing:
                clarity_score += 0.2
            
            return min(1.0, clarity_score)
            
        except Exception:
            return 0.5
    
    def _assess_information_density(self, content: str) -> float:
        """Assess information density"""
        try:
            words = content.split()
            # Calculate information density (words per meaningful concept)
            meaningful_words = [w for w in words if len(w) > 3]
            
            if len(meaningful_words) < 5:
                return 0.3  # Too sparse
            elif len(meaningful_words) > 30:
                return 0.9  # Dense but acceptable
            else:
                return 0.7  # Good density
                
        except Exception:
            return 0.5
    
    def _assess_emotional_context(self, metadata: Dict) -> float:
        """Assess emotional context richness"""
        emotional_tone = metadata.get('emotional_tone', 'neutral')
        importance = metadata.get('importance', 0.5)
        
        # Emotional richness scoring
        if emotional_tone == 'neutral':
            return 0.3
        else:
            return min(1.0, 0.6 + importance * 0.4)
    
    def _assess_personal_relevance(self, metadata: Dict) -> float:
        """Assess personal relevance"""
        importance = metadata.get('importance', 0.5)
        participants = metadata.get('participants', [])
        
        # Personal relevance based on importance and participant count
        personal_score = importance
        if len(participants) > 1:  # Social interaction
            personal_score += 0.1
        
        return min(1.0, personal_score)
    
    def _assess_temporal_relevance(self, metadata: Dict) -> float:
        """Assess temporal relevance"""
        try:
            # Handle both string and datetime timestamps
            def safe_datetime_convert(timestamp):
                if isinstance(timestamp, str):
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return timestamp
            
            timestamp = safe_datetime_convert(metadata['timestamp'])
            now = datetime.now()
            age_days = (now - timestamp).days
            
            if age_days == 0:
                return 1.0  # Very recent
            elif age_days < 7:
                return 0.9
            elif age_days < 30:
                return 0.7
            elif age_days < 90:
                return 0.5
            else:
                return 0.3
                
        except Exception:
            return 0.5
    
    def _categorize_quality(self, quality_score: float) -> str:
        """Categorize memory quality"""
        for category, threshold in self.quality_thresholds.items():
            if quality_score >= threshold:
                return category
        return 'poor'
    
    def _generate_quality_suggestions(self, quality_factors: Dict) -> List[str]:
        """Generate suggestions for memory quality improvement"""
        suggestions = []
        
        if quality_factors.get('content_clarity', 0.5) < 0.6:
            suggestions.append("Improve content clarity with better sentence structure")
        
        if quality_factors.get('information_density', 0.5) < 0.6:
            suggestions.append("Add more meaningful information to increase density")
        
        if quality_factors.get('emotional_context', 0.5) < 0.6:
            suggestions.append("Enhance emotional context and tone analysis")
        
        if quality_factors.get('personal_relevance', 0.5) < 0.6:
            suggestions.append("Increase personal relevance and importance scoring")
        
        if not suggestions:
            suggestions.append("Memory quality is good - maintain current standards")
        
        return suggestions

def create_enhanced_memory_retriever(memory_system: Any) -> HumanLikeMemoryRetriever:
    """Create enhanced memory retriever system"""
    return HumanLikeMemoryRetriever(memory_system)

def create_memory_quality_assessor(memory_system: Any) -> MemoryQualityAssessor:
    """Create memory quality assessor"""
    return MemoryQualityAssessor(memory_system)