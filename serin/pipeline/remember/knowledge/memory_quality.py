"""Memory quality assessment — clarity, density, relevance scoring."""
from typing import Dict, List
from serin.config.logger import logger


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