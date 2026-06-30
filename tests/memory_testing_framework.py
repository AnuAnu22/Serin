"""
Memory System Testing Framework
Comprehensive testing suite for memory retrieval, personality consistency, 
and human-like behavior validation without requiring LLM dependencies.
"""

import json
import time
import statistics
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
from logger_config import logger
import sqlite3

@dataclass
class TestScenario:
    """Memory retrieval test scenario"""
    name: str
    query: str
    expected_keywords: List[str]
    expected_memory_types: List[str]
    context_hints: Dict[str, Any]
    emotional_state: str = "neutral"
    conversation_phase: str = "casual"

@dataclass
class TestResult:
    """Test execution result"""
    scenario_name: str
    timestamp: str
    success: bool
    metrics: Dict[str, float]
    memories_retrieved: int
    relevant_memories: int
    precision: float
    recall: float
    relevance_scores: List[float]
    performance_time: float
    errors: List[str]

@dataclass
class PersonalityConsistencyTest:
    """Personality consistency test result"""
    user_id: str
    username: str
    declared_traits: List[str]
    declared_interests: List[str]
    memory_count: int
    trait_mentions: int
    interest_mentions: int
    consistency_score: float
    coherence_score: float

@dataclass
class SystemPerformanceMetrics:
    """System performance metrics"""
    timestamp: str
    memory_operations_per_second: float
    average_response_time: float
    error_rate: float
    database_health_score: float
    memory_accuracy_score: float
    personality_consistency_score: float

class MemorySystemTester:
    """Comprehensive testing framework for memory systems"""
    
    def __init__(self, memory_system, test_data_dir: str = "./test_results"):
        self.memory = memory_system
        self.test_data_dir = test_data_dir
        self.test_scenarios = self._initialize_test_scenarios()
        self.test_results = []
        self.performance_metrics = []
        
        import os
        os.makedirs(test_data_dir, exist_ok=True)
    
    def _initialize_test_scenarios(self) -> List[TestScenario]:
        """Initialize comprehensive test scenarios"""
        return [
            # Temporal memory tests
            TestScenario(
                name="recent_conversation_recall",
                query="What did we talk about cats yesterday?",
                expected_keywords=["cat", "cats", "kitten", "pet"],
                expected_memory_types=["conversation", "topic"],
                context_hints={"time_reference": "yesterday", "topic": "pets"},
                emotional_state="curious",
                conversation_phase="casual"
            ),
            
            TestScenario(
                name="weekly_topic_continuity",
                query="Remember our discussion about projects this week?",
                expected_keywords=["project", "work", "develop", "build"],
                expected_memory_types=["topic", "plan"],
                context_hints={"time_reference": "week", "topic": "projects"},
                emotional_state="focused",
                conversation_phase="focused"
            ),
            
            # Personality-based memory tests
            TestScenario(
                name="user_interests_recall",
                query="Tell me about Alice's hobbies",
                expected_keywords=["alice", "hobby", "like", "love", "interest"],
                expected_memory_types=["personal", "preference"],
                context_hints={"user": "alice", "type": "interests"},
                emotional_state="friendly",
                conversation_phase="casual"
            ),
            
            TestScenario(
                name="personality_trait_memory",
                query="How does Bob usually communicate?",
                expected_keywords=["bob", "communication", "style", "personality"],
                expected_memory_types=["personality", "style"],
                context_hints={"user": "bob", "type": "personality"},
                emotional_state="neutral",
                conversation_phase="analytical"
            ),
            
            # Contextual relevance tests
            TestScenario(
                name="conversation_continuity",
                query="What were we just discussing about the code?",
                expected_keywords=["code", "develop", "programming", "software"],
                expected_memory_types=["technical", "recent"],
                context_hints={"continuity": True, "technical": True},
                emotional_state="focused",
                conversation_phase="focused"
            ),
            
            TestScenario(
                name="emotional_context_memory",
                query="How was everyone feeling during our meeting?",
                expected_keywords=["meeting", "feel", "emotion", "mood"],
                expected_memory_types=["emotional", "social"],
                context_hints={"social": True, "emotional": True},
                emotional_state="empathetic",
                conversation_phase="emotional"
            ),
            
            # Relationship-based tests
            TestScenario(
                name="relationship_dynamics",
                query="How well do Alice and Bob know each other?",
                expected_keywords=["alice", "bob", "relationship", "know"],
                expected_memory_types=["relationship", "social"],
                context_hints={"users": ["alice", "bob"], "type": "relationship"},
                emotional_state="curious",
                conversation_phase="analytical"
            ),
            
            # Importance-based tests
            TestScenario(
                name="important_decisions",
                query="What important decisions have we made recently?",
                expected_keywords=["decision", "important", "choose", "decide"],
                expected_memory_types=["decision", "important"],
                context_hints={"importance": "high", "type": "decision"},
                emotional_state="serious",
                conversation_phase="focused"
            )
        ]
    
    def run_comprehensive_test_suite(self) -> Dict:
        """Run comprehensive test suite and return results"""
        logger.info("🧪 Starting comprehensive memory system test suite...")
        
        test_report = {
            "timestamp": datetime.now().isoformat(),
            "test_scenarios_run": 0,
            "total_tests": len(self.test_scenarios),
            "success_rate": 0.0,
            "average_metrics": {},
            "performance_analysis": {},
            "personality_consistency": {},
            "recommendations": [],
            "test_results": []
        }
        
        # Run all test scenarios
        for scenario in self.test_scenarios:
            try:
                result = self._run_single_test_scenario(scenario)
                test_report["test_results"].append(asdict(result))
                test_report["test_scenarios_run"] += 1
                
                if result.success:
                    test_report["success_rate"] += 1
                
            except Exception as e:
                logger.error(f" Test scenario {scenario.name} failed: {e}")
                error_result = TestResult(
                    scenario_name=scenario.name,
                    timestamp=datetime.now().isoformat(),
                    success=False,
                    metrics={},
                    memories_retrieved=0,
                    relevant_memories=0,
                    precision=0.0,
                    recall=0.0,
                    relevance_scores=[],
                    performance_time=0.0,
                    errors=[str(e)]
                )
                test_report["test_results"].append(asdict(error_result))
        
        # Calculate aggregate metrics
        test_report["success_rate"] = test_report["success_rate"] / test_report["test_scenarios_run"] if test_report["test_scenarios_run"] > 0 else 0.0
        test_report["average_metrics"] = self._calculate_average_metrics(test_report["test_results"])
        test_report["performance_analysis"] = self._analyze_performance(test_report["test_results"])
        test_report["personality_consistency"] = self._test_personality_consistency()
        test_report["recommendations"] = self._generate_test_recommendations(test_report)
        
        # Save test report
        self._save_test_report(test_report)
        
        logger.info(f" Test suite completed - Success rate: {test_report['success_rate']:.2%}")
        return test_report
    
    def _run_single_test_scenario(self, scenario: TestScenario) -> TestResult:
        """Run a single test scenario"""
        logger.debug(f"🧪 Running test scenario: {scenario.name}")
        
        start_time = time.time()
        errors = []
        
        try:
            # Execute memory search
            memories = self.memory.search_memories(
                query=scenario.query,
                n_results=10
            )
            
            # Analyze results
            relevant_memories = self._analyze_relevance(memories, scenario)
            precision = self._calculate_precision(memories, scenario)
            recall = self._calculate_recall(memories, scenario)
            relevance_scores = [mem.get('relevance', 0) for mem in memories]
            
            # Calculate additional metrics
            metrics = {
                "relevance_score": sum(relevance_scores) / max(1, len(relevance_scores)),
                "temporal_relevance": self._assess_temporal_relevance(memories),
                "context_appropriateness": self._assess_context_appropriateness(memories, scenario),
                "emotional_consistency": self._assess_emotional_consistency(memories, scenario)
            }
            
            success = precision > 0.3 and len(memories) > 0  # Basic success criteria
            
        except Exception as e:
            logger.error(f" Test scenario execution failed: {e}")
            memories = []
            relevant_memories = 0
            precision = 0.0
            recall = 0.0
            relevance_scores = []
            metrics = {}
            errors.append(str(e))
            success = False
        
        execution_time = time.time() - start_time
        
        result = TestResult(
            scenario_name=scenario.name,
            timestamp=datetime.now().isoformat(),
            success=success,
            metrics=metrics,
            memories_retrieved=len(memories),
            relevant_memories=relevant_memories,
            precision=precision,
            recall=recall,
            relevance_scores=relevance_scores,
            performance_time=execution_time,
            errors=errors
        )
        
        self.test_results.append(result)
        return result
    
    def _analyze_relevance(self, memories: List[Dict], scenario: TestScenario) -> int:
        """Analyze relevance of retrieved memories"""
        relevant_count = 0
        
        for memory in memories:
            content = memory.get('content', '').lower()
            expected_keywords = [kw.lower() for kw in scenario.expected_keywords]
            
            # Check keyword matches
            keyword_matches = sum(1 for kw in expected_keywords if kw in content)
            
            # Check memory type appropriateness
            memory_type_match = self._check_memory_type_match(memory, scenario.expected_memory_types)
            
            # Score relevance
            relevance_score = (keyword_matches / max(1, len(expected_keywords))) * 0.7 + memory_type_match * 0.3
            
            if relevance_score > 0.3:  # Threshold for relevance
                relevant_count += 1
        
        return relevant_count
    
    def _check_memory_type_match(self, memory: Dict, expected_types: List[str]) -> float:
        """Check if memory type matches expected types"""
        # Simple heuristic - in real implementation, this would be more sophisticated
        content = memory.get('content', '').lower()
        
        type_indicators = {
            "conversation": ["said", "mentioned", "discussed", "talked"],
            "personal": ["i ", "my ", "me ", "myself"],
            "emotional": ["feel", "happy", "sad", "excited", "worried"],
            "technical": ["code", "program", "develop", "build", "software"],
            "relationship": ["know", "friend", "relationship", "close"],
            "decision": ["decided", "choose", "agree", "disagree"],
            "important": ["important", "significant", "crucial", "vital"]
        }
        
        match_score = 0
        for expected_type in expected_types:
            indicators = type_indicators.get(expected_type, [])
            type_matches = sum(1 for indicator in indicators if indicator in content)
            if type_matches > 0:
                match_score += type_matches / len(indicators)
        
        return min(1.0, match_score / len(expected_types))
    
    def _calculate_precision(self, memories: List[Dict], scenario: TestScenario) -> float:
        """Calculate precision (relevant retrieved / total retrieved)"""
        if len(memories) == 0:
            return 0.0
        
        relevant_count = self._analyze_relevance(memories, scenario)
        return relevant_count / len(memories)
    
    def _calculate_recall(self, memories: List[Dict], scenario: TestScenario) -> float:
        """Calculate recall (relevant retrieved / relevant available)"""
        # This is simplified - in reality, we'd need to know total relevant memories
        relevant_count = self._analyze_relevance(memories, scenario)
        
        # Estimate recall based on retrieved relevant count
        # Better memories should have higher recall
        total_possible_relevant = len([mem for mem in memories if mem.get('relevance', 0) > 0.5])
        
        if total_possible_relevant == 0:
            return 0.5  # Neutral score if no highly relevant memories found
        
        return min(1.0, relevant_count / total_possible_relevant)
    
    def _assess_temporal_relevance(self, memories: List[Dict]) -> float:
        """Assess temporal relevance of memories"""
        if not memories:
            return 0.0
        
        now = datetime.now()
        temporal_scores = []
        
        for memory in memories:
            try:
                # Handle both string and datetime timestamps
                def safe_datetime_convert(timestamp):
                    if isinstance(timestamp, str):
                        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    return timestamp
                
                timestamp = safe_datetime_convert(memory['timestamp'])
                age_days = (now - timestamp).days
                
                # Human-like temporal relevance curve
                if age_days == 0:
                    score = 1.0
                elif age_days < 7:
                    score = 0.9 - (age_days * 0.05)
                elif age_days < 30:
                    score = 0.7 - ((age_days - 7) * 0.01)
                else:
                    score = max(0.1, 0.3 - ((age_days - 30) * 0.005))
                
                temporal_scores.append(score)
                
            except Exception:
                temporal_scores.append(0.5)  # Default for invalid timestamps
        
        return sum(temporal_scores) / len(temporal_scores)
    
    def _assess_context_appropriateness(self, memories: List[Dict], scenario: TestScenario) -> float:
        """Assess context appropriateness"""
        # Simple context matching based on scenario hints
        context_hints = scenario.context_hints
        
        appropriateness_scores = []
        for memory in memories:
            content = memory.get('content', '').lower()
            score = 0.5  # Base score
            
            # Check for topic matches
            if "topic" in context_hints:
                topic = context_hints["topic"].lower()
                if topic in content:
                    score += 0.3
            
            # Check for user matches
            if "user" in context_hints:
                user = context_hints["user"].lower()
                if user in content:
                    score += 0.3
            
            # Check for technical content
            if context_hints.get("technical"):
                technical_words = ["code", "program", "develop", "software", "build"]
                if any(word in content for word in technical_words):
                    score += 0.2
            
            # Check for social content
            if context_hints.get("social"):
                social_words = ["people", "team", "group", "meeting", "discuss"]
                if any(word in content for word in social_words):
                    score += 0.2
            
            appropriateness_scores.append(min(1.0, score))
        
        return sum(appropriateness_scores) / len(appropriateness_scores)
    
    def _assess_emotional_consistency(self, memories: List[Dict], scenario: TestScenario) -> float:
        """Assess emotional consistency with scenario"""
        target_emotion = scenario.emotional_state
        
        emotional_keywords = {
            "friendly": ["nice", "good", "great", "awesome", "cool", "happy"],
            "curious": ["what", "how", "why", "interested", "wonder"],
            "empathetic": ["understand", "feel", "sorry", "support", "care"],
            "focused": ["important", "need", "must", "should", "focus"],
            "serious": ["serious", "important", "critical", "significant"],
            "neutral": []  # Any content is acceptable
        }
        
        target_words = emotional_keywords.get(target_emotion, [])
        
        if not target_words:
            return 0.8  # Neutral emotion accepts anything
        
        consistency_scores = []
        for memory in memories:
            content = memory.get('content', '').lower()
            matches = sum(1 for word in target_words if word in content)
            consistency_score = min(1.0, matches / max(1, len(target_words)))
            consistency_scores.append(consistency_score)
        
        return sum(consistency_scores) / len(consistency_scores)
    
    def _calculate_average_metrics(self, test_results: List[Dict]) -> Dict:
        """Calculate average metrics across all tests"""
        if not test_results:
            return {}
        
        # Extract metrics
        precisions = [r.get('precision', 0) for r in test_results]
        recalls = [r.get('recall', 0) for r in test_results]
        response_times = [r.get('performance_time', 0) for r in test_results]
        
        # Extract custom metrics
        relevance_scores = []
        temporal_relevance_scores = []
        context_appropriateness_scores = []
        emotional_consistency_scores = []
        
        for result in test_results:
            metrics = result.get('metrics', {})
            relevance_scores.append(metrics.get('relevance_score', 0))
            temporal_relevance_scores.append(metrics.get('temporal_relevance', 0))
            context_appropriateness_scores.append(metrics.get('context_appropriateness', 0))
            emotional_consistency_scores.append(metrics.get('emotional_consistency', 0))
        
        return {
            "average_precision": round(statistics.mean(precisions), 3) if precisions else 0,
            "average_recall": round(statistics.mean(recalls), 3) if recalls else 0,
            "average_response_time": round(statistics.mean(response_times), 3) if response_times else 0,
            "average_relevance_score": round(statistics.mean(relevance_scores), 3) if relevance_scores else 0,
            "average_temporal_relevance": round(statistics.mean(temporal_relevance_scores), 3) if temporal_relevance_scores else 0,
            "average_context_appropriateness": round(statistics.mean(context_appropriateness_scores), 3) if context_appropriateness_scores else 0,
            "average_emotional_consistency": round(statistics.mean(emotional_consistency_scores), 3) if emotional_consistency_scores else 0
        }
    
    def _analyze_performance(self, test_results: List[Dict]) -> Dict:
        """Analyze performance characteristics"""
        if not test_results:
            return {}
        
        response_times = [r.get('performance_time', 0) for r in test_results]
        success_count = sum(1 for r in test_results if r.get('success', False))
        
        performance_analysis = {
            "total_tests": len(test_results),
            "successful_tests": success_count,
            "success_rate": round(success_count / len(test_results), 3),
            "average_response_time": round(statistics.mean(response_times), 3),
            "median_response_time": round(statistics.median(response_times), 3),
            "max_response_time": round(max(response_times), 3),
            "min_response_time": round(min(response_times), 3),
            "response_time_std_dev": round(statistics.stdev(response_times) if len(response_times) > 1 else 0, 3)
        }
        
        # Performance categories
        if performance_analysis["average_response_time"] < 0.1:
            performance_analysis["performance_category"] = "excellent"
        elif performance_analysis["average_response_time"] < 0.5:
            performance_analysis["performance_category"] = "good"
        elif performance_analysis["average_response_time"] < 1.0:
            performance_analysis["performance_category"] = "acceptable"
        else:
            performance_analysis["performance_category"] = "poor"
        
        return performance_analysis
    
    def _test_personality_consistency(self) -> Dict:
        """Test personality consistency across users"""
        logger.debug(" Testing personality consistency...")
        
        try:
            cursor = self.memory.conn.cursor()
            
            # Get users with personality traits
            cursor.execute("""
                SELECT user_id, username, personality_traits, interests 
                FROM users 
                WHERE personality_traits IS NOT NULL OR interests IS NOT NULL
            """)
            
            users = cursor.fetchall()
            consistency_results = []
            
            for user in users:
                user_id = user['user_id']
                username = user['username']
                traits = json.loads(user['personality_traits'] or '[]')
                interests = json.loads(user['interests'] or '[]')
                
                # Get user's memories
                user_memories = self.memory.memories.get(
                    where={"user_id": user_id},
                    limit=50
                )
                
                if user_memories and user_memories.get('documents'):
                    documents = user_memories['documents']
                    
                    # Analyze trait consistency
                    trait_mentions = sum(1 for trait in traits for doc in documents if trait.lower() in doc.lower())
                    trait_consistency = trait_mentions / max(1, len(traits) * len(documents) * 0.01)  # Normalized
                    
                    # Analyze interest consistency
                    interest_mentions = sum(1 for interest in interests for doc in documents if interest.lower() in doc.lower())
                    interest_consistency = interest_mentions / max(1, len(interests) * len(documents) * 0.01)  # Normalized
                    
                    # Calculate overall consistency score
                    overall_consistency = (trait_consistency + interest_consistency) / 2
                    
                    consistency_result = PersonalityConsistencyTest(
                        user_id=user_id,
                        username=username,
                        declared_traits=traits,
                        declared_interests=interests,
                        memory_count=len(documents),
                        trait_mentions=trait_mentions,
                        interest_mentions=interest_mentions,
                        consistency_score=round(min(1.0, overall_consistency), 3),
                        coherence_score=round(min(1.0, trait_consistency * 0.6 + interest_consistency * 0.4), 3)
                    )
                    
                    consistency_results.append(asdict(consistency_result))
            
            # Calculate aggregate consistency metrics
            if consistency_results:
                consistency_scores = [r['consistency_score'] for r in consistency_results]
                coherence_scores = [r['coherence_score'] for r in consistency_results]
                
                aggregate_metrics = {
                    "users_tested": len(consistency_results),
                    "average_consistency_score": round(statistics.mean(consistency_scores), 3),
                    "average_coherence_score": round(statistics.mean(coherence_scores), 3),
                    "users_with_high_consistency": sum(1 for score in consistency_scores if score > 0.7),
                    "consistency_distribution": dict(Counter([round(score, 1) for score in consistency_scores]))
                }
            else:
                aggregate_metrics = {
                    "users_tested": 0,
                    "note": "No users with personality traits found"
                }
            
            return {
                "individual_results": consistency_results,
                "aggregate_metrics": aggregate_metrics
            }
            
        except Exception as e:
            logger.error(f" Personality consistency testing failed: {e}")
            return {"error": str(e)}
    
    def _generate_test_recommendations(self, test_report: Dict) -> List[str]:
        """Generate recommendations based on test results"""
        recommendations = []
        
        avg_metrics = test_report.get("average_metrics", {})
        performance = test_report.get("performance_analysis", {})
        personality = test_report.get("personality_consistency", {})
        
        # Precision/Recall recommendations
        precision = avg_metrics.get("average_precision", 0)
        recall = avg_metrics.get("average_recall", 0)
        
        if precision < 0.5:
            recommendations.append(" Improve memory retrieval precision - too many irrelevant memories being returned")
        elif precision > 0.8:
            recommendations.append(" Excellent precision - retrieval is highly relevant")
        
        if recall < 0.4:
            recommendations.append(" Increase memory retrieval recall - missing relevant memories")
        elif recall > 0.7:
            recommendations.append(" Good recall - finding most relevant memories")
        
        # Performance recommendations
        avg_response_time = performance.get("average_response_time", 0)
        if avg_response_time > 1.0:
            recommendations.append(" Optimize memory retrieval performance - response time too slow")
        elif avg_response_time < 0.1:
            recommendations.append(" Excellent performance - fast retrieval times")
        
        # Personality consistency recommendations
        personality_metrics = personality.get("aggregate_metrics", {})
        avg_consistency = personality_metrics.get("average_consistency_score", 0)
        if avg_consistency < 0.5:
            recommendations.append(" Improve personality consistency - user traits not well reflected in memories")
        elif avg_consistency > 0.7:
            recommendations.append(" Good personality consistency - user traits well represented")
        
        # Context appropriateness
        context_appropriateness = avg_metrics.get("average_context_appropriateness", 0)
        if context_appropriateness < 0.6:
            recommendations.append(" Improve context appropriateness - memories don't match conversation context well")
        
        # Emotional consistency
        emotional_consistency = avg_metrics.get("average_emotional_consistency", 0)
        if emotional_consistency < 0.6:
            recommendations.append(" Enhance emotional consistency - tone doesn't match conversation mood")
        
        # Temporal relevance
        temporal_relevance = avg_metrics.get("average_temporal_relevance", 0)
        if temporal_relevance < 0.6:
            recommendations.append("⏰ Improve temporal relevance - too many outdated memories")
        
        # Overall system health
        success_rate = performance.get("success_rate", 0)
        if success_rate < 0.7:
            recommendations.append(" System health needs attention - low test success rate")
        elif success_rate > 0.9:
            recommendations.append(" System is healthy - high test success rate")
        
        if not recommendations:
            recommendations.append(" Memory system is performing well - no major issues detected")
        
        return recommendations
    
    def _save_test_report(self, test_report: Dict):
        """Save test report to file"""
        try:
            report_file = f"{self.test_data_dir}/test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            with open(report_file, 'w') as f:
                json.dump(test_report, f, indent=2, default=str)
            
            logger.info(f" Test report saved: {report_file}")
            
        except Exception as e:
            logger.error(f" Failed to save test report: {e}")
    
    def run_performance_benchmark(self, iterations: int = 100) -> Dict:
        """Run performance benchmark test"""
        logger.info(f" Running performance benchmark ({iterations} iterations)...")
        
        benchmark_results = {
            "timestamp": datetime.now().isoformat(),
            "iterations": iterations,
            "test_queries": [
                "test memory retrieval",
                "user conversation topic",
                "recent discussion about projects",
                "Alice's interests and hobbies",
                "important decisions made"
            ]
        }
        
        response_times = []
        error_count = 0
        
        for i in range(iterations):
            query = benchmark_results["test_queries"][i % len(benchmark_results["test_queries"])]
            
            try:
                start_time = time.time()
                results = self.memory.search_memories(query=query, n_results=5)
                end_time = time.time()
                
                response_time = end_time - start_time
                response_times.append(response_time)
                
            except Exception as e:
                logger.error(f" Benchmark iteration {i} failed: {e}")
                error_count += 1
        
        # Calculate performance statistics
        if response_times:
            benchmark_results.update({
                "average_response_time": round(statistics.mean(response_times), 3),
                "median_response_time": round(statistics.median(response_times), 3),
                "min_response_time": round(min(response_times), 3),
                "max_response_time": round(max(response_times), 3),
                "std_deviation": round(statistics.stdev(response_times), 3) if len(response_times) > 1 else 0,
                "percentile_95": round(sorted(response_times)[int(len(response_times) * 0.95)], 3),
                "percentile_99": round(sorted(response_times)[int(len(response_times) * 0.99)], 3)
            })
        
        benchmark_results.update({
            "error_count": error_count,
            "error_rate": round(error_count / iterations, 3),
            "throughput": round(iterations / sum(response_times), 2) if response_times else 0
        })
        
        # Save benchmark results
        try:
            benchmark_file = f"{self.test_data_dir}/performance_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(benchmark_file, 'w') as f:
                json.dump(benchmark_results, f, indent=2)
            logger.info(f" Benchmark results saved: {benchmark_file}")
        except Exception as e:
            logger.error(f" Failed to save benchmark results: {e}")
        
        return benchmark_results

def create_memory_system_tester(memory_system):
    """Create and return memory system tester instance"""
    return MemorySystemTester(memory_system)