"""
Memory System Diagnostic Toolkit
Provides comprehensive debugging and analysis capabilities for the memory system
without requiring LLM dependencies.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from logger_config import logger
try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
from collections import Counter, defaultdict

@dataclass
class MemoryDiagnosticReport:
    """Structure for diagnostic report data"""
    timestamp: str
    database_health: Dict
    memory_statistics: Dict
    retrieval_analysis: Dict
    personality_consistency: Dict
    temporal_analysis: Dict
    recommendations: List[str]
    critical_issues: List[str]

class MemorySystemDiagnostic:
    """Comprehensive diagnostic tool for memory system analysis"""
    
    def __init__(self, memory_system, test_data_dir: str = "./diagnostic_data"):
        self.memory = memory_system
        self.test_data_dir = test_data_dir
        os.makedirs(test_data_dir, exist_ok=True)
        
        # Diagnostic constants
        self.TEST_CONVERSATIONS = [
            {
                "query": "What did we talk about cats yesterday?",
                "expected_keywords": ["cat", "cats", "kitten", "pet"],
                "context": "Testing temporal memory retrieval"
            },
            {
                "query": "Tell me about Alice's interests",
                "expected_keywords": ["alice", "hobby", "like", "love", "interest"],
                "context": "Testing user personality memory"
            },
            {
                "query": "What projects are we working on?",
                "expected_keywords": ["project", "work", "develop", "build"],
                "context": "Testing topic continuity memory"
            }
        ]
    
    def run_comprehensive_diagnostic(self) -> MemoryDiagnosticReport:
        """Run full diagnostic suite and return report"""
        logger.info(" Starting comprehensive memory system diagnostic...")
        
        report = MemoryDiagnosticReport(
            timestamp=datetime.now().isoformat(),
            database_health=self._analyze_database_health(),
            memory_statistics=self._analyze_memory_statistics(),
            retrieval_analysis=self._analyze_retrieval_patterns(),
            personality_consistency=self._analyze_personality_consistency(),
            temporal_analysis=self._analyze_temporal_patterns(),
            recommendations=[],
            critical_issues=[]
        )
        
        # Generate recommendations and identify issues
        report.recommendations = self._generate_recommendations(report)
        report.critical_issues = self._identify_critical_issues(report)
        
        # Save diagnostic report
        self._save_diagnostic_report(report)
        
        logger.info(" Comprehensive diagnostic completed")
        return report
    
    def _analyze_database_health(self) -> Dict:
        """Analyze database integrity and health"""
        logger.debug("🗄 Analyzing database health...")
        
        health_status = {
            "sqlite_connection": self._check_sqlite_health(),
            "chroma_connection": self._check_chroma_health(),
            "schema_integrity": self._check_schema_integrity(),
            "data_consistency": self._check_data_consistency(),
            "backup_status": self._check_backup_status()
        }
        
        # Calculate overall health score
        health_scores = {
            "sqlite": 100 if health_status["sqlite_connection"] else 0,
            "chroma": 100 if health_status["chroma_connection"] else 0,
            "schema": health_status["schema_integrity"]["score"],
            "consistency": health_status["data_consistency"]["score"]
        }
        
        overall_health = sum(health_scores.values()) / len(health_scores)
        health_status["overall_score"] = round(overall_health, 2)
        health_status["health_scores"] = health_scores
        
        return health_status
    
    def _check_sqlite_health(self) -> bool:
        """Check SQLite connection and basic operations"""
        try:
            cursor = self.memory.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sqlite_master")
            cursor.fetchone()
            return True
        except Exception as e:
            logger.error(f" SQLite health check failed: {e}")
            return False
    
    def _check_chroma_health(self) -> bool:
        """Check ChromaDB connection and basic operations.
        
        Returns True if ChromaDB is healthy, or if using Qdrant (skips check).
        """
        if not CHROMADB_AVAILABLE:
            logger.debug("ChromaDB not available - skipping check (using Qdrant)")
            return True
        if not hasattr(self.memory, 'memories'):
            logger.debug("Memory system has no .memories attribute - likely Qdrant, skipping check")
            return True
        try:
            count = self.memory.memories.count()
            logger.debug(f"ChromaDB health check passed - {count} memories")
            return True
        except Exception as e:
            logger.error(f"ChromaDB health check failed: {e}")
            return False
    
    def _check_schema_integrity(self) -> Dict:
        """Check database schema integrity"""
        try:
            cursor = self.memory.conn.cursor()
            
            # Check required tables
            required_tables = ['users', 'relationships', 'activity_log', 'recent_messages']
            tables_status = {}
            
            for table in required_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                tables_status[table] = {"exists": True, "count": count}
            
            # Check table structures
            schema_status = {}
            for table in required_tables:
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cursor.fetchall()]
                schema_status[table] = {
                    "columns": columns,
                    "column_count": len(columns)
                }
            
            return {
                "tables": tables_status,
                "schema": schema_status,
                "score": 95  # High score if tables exist and have reasonable structure
            }
            
        except Exception as e:
            logger.error(f" Schema integrity check failed: {e}")
            return {"error": str(e), "score": 0}
    
    def _check_data_consistency(self) -> Dict:
        """Check data consistency across tables"""
        try:
            cursor = self.memory.conn.cursor()
            
            consistency_checks = {}
            
            # Check user consistency
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT user_id) FROM recent_messages")
            recent_user_count = cursor.fetchone()[0]
            
            consistency_checks["user_consistency"] = {
                "users_table": user_count,
                "recent_messages_users": recent_user_count,
                "consistency_ratio": round(recent_user_count / max(1, user_count), 3)
            }
            
            # Check for orphaned records
            cursor.execute("""
                SELECT COUNT(*) FROM recent_messages rm
                LEFT JOIN users u ON rm.user_id = u.user_id
                WHERE u.user_id IS NULL
            """)
            orphaned_messages = cursor.fetchone()[0]
            
            consistency_checks["orphaned_records"] = {
                "count": orphaned_messages,
                "has_orphans": orphaned_messages > 0
            }
            
            # Calculate consistency score
            score = 100
            if orphaned_messages > 0:
                score -= min(20, orphaned_messages * 2)
            if consistency_checks["user_consistency"]["consistency_ratio"] < 0.5:
                score -= 10
            
            return {
                **consistency_checks,
                "score": max(0, score)
            }
            
        except Exception as e:
            logger.error(f" Data consistency check failed: {e}")
            return {"error": str(e), "score": 0}
    
    def _check_backup_status(self) -> Dict:
        """Check backup system status"""
        try:
            backup_dir = "./bot_data/backups"
            if not os.path.exists(backup_dir):
                return {"exists": False, "backups_found": 0}
            
            backups = [f for f in os.listdir(backup_dir) if f.endswith('.tar.gz')]
            
            # Check backup freshness
            recent_backups = []
            now = datetime.now()
            for backup in backups:
                backup_path = os.path.join(backup_dir, backup)
                if os.path.exists(backup_path):
                    mtime = datetime.fromtimestamp(os.path.getmtime(backup_path))
                    if (now - mtime).days < 1:
                        recent_backups.append(backup)
            
            return {
                "exists": True,
                "backups_found": len(backups),
                "recent_backups": recent_backups,
                "backup_freshness": "good" if len(recent_backups) > 0 else "concerning"
            }
            
        except Exception as e:
            logger.error(f" Backup status check failed: {e}")
            return {"error": str(e)}
    
    def _analyze_memory_statistics(self) -> Dict:
        """Analyze memory system statistics"""
        logger.debug(" Analyzing memory statistics...")
        
        stats = {
            "total_memories": 0,
            "total_users": 0,
            "memory_distribution": {},
            "user_activity": {},
            "temporal_distribution": {},
            "importance_distribution": {}
        }
        
        try:
            # Get basic stats from memory system
            memory_stats = self.memory.get_stats()
            stats.update(memory_stats)
            
            # Analyze ChromaDB memory distribution
            memories = self.memory.memories.get()
            if memories and memories.get('documents'):
                documents = memories['documents']
                metadatas = memories['metadatas']
                
                # Analyze memory content length distribution
                content_lengths = [len(doc) for doc in documents]
                stats["memory_distribution"] = {
                    "avg_length": round(sum(content_lengths) / len(content_lengths), 2),
                    "min_length": min(content_lengths),
                    "max_length": max(content_lengths),
                    "length_std": round((sum((x - sum(content_lengths)/len(content_lengths))**2 for x in content_lengths) / len(content_lengths))**0.5, 2)
                }
                
                # Analyze user distribution
                user_counts = Counter(meta['user_id'] for meta in metadatas)
                stats["user_activity"] = {
                    "most_active_user": user_counts.most_common(1)[0] if user_counts else None,
                    "user_distribution": dict(user_counts.most_common(5))
                }
                
                # Analyze temporal distribution
                timestamps = [meta['timestamp'] for meta in metadatas]
                date_counts = Counter(ts.split('T')[0] for ts in timestamps)
                stats["temporal_distribution"] = {
                    "dates_with_activity": len(date_counts),
                    "avg_memories_per_day": round(len(documents) / max(1, len(date_counts)), 2),
                    "most_active_date": date_counts.most_common(1)[0] if date_counts else None
                }
                
                # Analyze importance distribution
                importances = [float(meta['importance']) for meta in metadatas]
                importance_bins = [0, 0.25, 0.5, 0.75, 1.0]
                importance_distribution = {}
                for i in range(len(importance_bins) - 1):
                    count = sum(1 for imp in importances if importance_bins[i] <= imp < importance_bins[i+1])
                    importance_distribution[f"{importance_bins[i]}-{importance_bins[i+1]}"] = count
                
                stats["importance_distribution"] = {
                    **importance_distribution,
                    "avg_importance": round(sum(importances) / len(importances), 3),
                    "high_importance_ratio": round(sum(1 for imp in importances if imp > 0.7) / len(importances), 3)
                }
                
                stats["total_memories"] = len(documents)
                
        except Exception as e:
            logger.error(f" Memory statistics analysis failed: {e}")
            stats["error"] = str(e)
        
        return stats
    
    def _analyze_retrieval_patterns(self) -> Dict:
        """Analyze memory retrieval patterns and accuracy"""
        logger.debug(" Analyzing retrieval patterns...")
        
        analysis = {
            "test_scenarios": [],
            "semantic_accuracy": {},
            "context_effectiveness": {},
            "temporal_relevance": {}
        }
        
        # Test different retrieval scenarios
        for scenario in self.TEST_CONVERSATIONS:
            try:
                # Test memory retrieval
                results = self.memory.search_memories(
                    query=scenario["query"],
                    n_results=10
                )
                
                # Analyze retrieval results
                relevant_count = 0
                context_relevance = []
                
                for result in results:
                    content = result.get('content', '').lower()
                    expected_keywords = [kw.lower() for kw in scenario["expected_keywords"]]
                    
                    # Check keyword relevance
                    keyword_matches = sum(1 for kw in expected_keywords if kw in content)
                    if keyword_matches > 0:
                        relevant_count += 1
                    
                    # Analyze context relevance (simple heuristic)
                    if result.get('relevance', 0) > 0.5:
                        context_relevance.append(result['relevance'])
                
                # Calculate metrics
                precision = relevant_count / max(1, len(results))
                avg_context_relevance = sum(context_relevance) / max(1, len(context_relevance))
                
                analysis["test_scenarios"].append({
                    "scenario": scenario["context"],
                    "query": scenario["query"],
                    "results_found": len(results),
                    "precision": round(precision, 3),
                    "avg_context_relevance": round(avg_context_relevance, 3),
                    "relevant_results": relevant_count
                })
                
            except Exception as e:
                logger.error(f" Test scenario failed: {e}")
                analysis["test_scenarios"].append({
                    "scenario": scenario["context"],
                    "error": str(e)
                })
        
        return analysis
    
    def _analyze_personality_consistency(self) -> Dict:
        """Analyze personality trait consistency across memories"""
        logger.debug(" Analyzing personality consistency...")
        
        consistency = {
            "user_profiles": {},
            "personality_coherence": {},
            "trait_stability": {}
        }
        
        try:
            cursor = self.memory.conn.cursor()
            
            # Get all users with personality traits
            cursor.execute("""
                SELECT user_id, username, personality_traits, interests 
                FROM users 
                WHERE personality_traits IS NOT NULL OR interests IS NOT NULL
            """)
            
            users = cursor.fetchall()
            
            for user in users:
                user_id = user['user_id']
                traits = json.loads(user['personality_traits'] or '[]')
                interests = json.loads(user['interests'] or '[]')
                
                # Get user's memories for comparison
                user_memories = self.memory.memories.get(
                    where={"user_id": user_id},
                    limit=50
                )
                
                if user_memories and user_memories.get('documents'):
                    documents = user_memories['documents']
                    
                    # Simple personality consistency check
                    # (In a real implementation, this would use NLP analysis)
                    trait_mentions = sum(1 for trait in traits for doc in documents if trait.lower() in doc.lower())
                    interest_mentions = sum(1 for interest in interests for doc in documents if interest.lower() in doc.lower())
                    
                    consistency["user_profiles"][user_id] = {
                        "username": user['username'],
                        "declared_traits": traits,
                        "declared_interests": interests,
                        "trait_consistency_score": round(trait_mentions / max(1, len(traits)), 3),
                        "interest_consistency_score": round(interest_mentions / max(1, len(interests)), 3),
                        "memory_count": len(documents)
                    }
            
        except Exception as e:
            logger.error(f" Personality consistency analysis failed: {e}")
            consistency["error"] = str(e)
        
        return consistency
    
    def _analyze_temporal_patterns(self) -> Dict:
        """Analyze temporal memory patterns and decay"""
        logger.debug("⏰ Analyzing temporal patterns...")
        
        temporal = {
            "memory_age_distribution": {},
            "retention_patterns": {},
            "temporal_coherence": {}
        }
        
        try:
            memories = self.memory.memories.get(limit=1000)  # Sample for analysis
            
            if memories and memories.get('documents'):
                documents = memories['documents']
                metadatas = memories['metadatas']
                
                # Analyze memory age distribution
                now = datetime.now()
                age_distribution = {}
                
                # Helper function to safely convert timestamps
                def safe_datetime_convert(timestamp):
                    """Safely convert timestamp to datetime, handling both string and datetime inputs"""
                    if isinstance(timestamp, str):
                        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    return timestamp
                
                for metadata in metadatas:
                    timestamp = safe_datetime_convert(metadata['timestamp'])
                    age_days = (now - timestamp).days
                    
                    # Categorize by age
                    if age_days < 1:
                        category = "today"
                    elif age_days < 7:
                        category = "week"
                    elif age_days < 30:
                        category = "month"
                    else:
                        category = "older"
                    
                    age_distribution[category] = age_distribution.get(category, 0) + 1
                
                temporal["memory_age_distribution"] = age_distribution
                
                # Analyze retention patterns (memories with high importance should be retained longer)
                importance_by_age = defaultdict(list)
                for metadata in metadatas:
                    timestamp = safe_datetime_convert(metadata['timestamp'])
                    age_days = (now - timestamp).days
                    importance_by_age[age_days].append(float(metadata['importance']))
                
                # Calculate retention score
                retention_scores = {}
                for age_days, importances in importance_by_age.items():
                    avg_importance = sum(importances) / len(importances)
                    retention_scores[f"{age_days}_days_old"] = round(avg_importance, 3)
                
                temporal["retention_patterns"] = dict(retention_scores)
                
        except Exception as e:
            logger.error(f" Temporal pattern analysis failed: {e}")
            temporal["error"] = str(e)
        
        return temporal
    
    def _generate_recommendations(self, report: MemoryDiagnosticReport) -> List[str]:
        """Generate actionable recommendations based on diagnostic results"""
        recommendations = []
        
        # Database health recommendations
        if report.database_health.get("overall_score", 0) < 90:
            recommendations.append(" Improve database health score through schema optimization and data cleanup")
        
        if report.database_health.get("data_consistency", {}).get("orphaned_records", 0) > 0:
            recommendations.append(" Clean up orphaned records in recent_messages table")
        
        # Memory retrieval recommendations
        low_precision_scenarios = [s for s in report.retrieval_analysis.get("test_scenarios", []) if s.get("precision", 0) < 0.3]
        if low_precision_scenarios:
            recommendations.append(f" Improve retrieval precision for {len(low_precision_scenarios)} test scenarios")
        
        # Personality consistency recommendations
        inconsistent_users = [uid for uid, profile in report.personality_consistency.get("user_profiles", {}).items() 
                            if profile.get("trait_consistency_score", 1) < 0.5]
        if inconsistent_users:
            recommendations.append(f" Enhance personality trait consistency for {len(inconsistent_users)} users")
        
        # Temporal recommendations
        very_old_memories = report.temporal_analysis.get("memory_age_distribution", {}).get("older", 0)
        if very_old_memories > 100:
            recommendations.append("⏰ Implement memory archival strategy for older memories")
        
        if not recommendations:
            recommendations.append(" System is performing well - continue monitoring")
        
        return recommendations
    
    def _identify_critical_issues(self, report: MemoryDiagnosticReport) -> List[str]:
        """Identify critical issues requiring immediate attention"""
        critical_issues = []
        
        # Database connectivity issues
        if not report.database_health.get("sqlite_connection", True):
            critical_issues.append(" SQLite database connection failed - system unusable")
        
        if not report.database_health.get("chroma_connection", True):
            critical_issues.append(" ChromaDB connection failed - memory retrieval unavailable")
        
        # Very low overall health score
        overall_score = report.database_health.get("overall_score", 0)
        if overall_score < 50:
            critical_issues.append(f" Critical: Database health score critically low ({overall_score})")
        
        # Data loss indicators
        orphaned_count = report.database_health.get("data_consistency", {}).get("orphaned_records", 0)
        if orphaned_count > 50:
            critical_issues.append(f" Data integrity issue: {orphaned_count} orphaned records detected")
        
        return critical_issues
    
    def _save_diagnostic_report(self, report: MemoryDiagnosticReport):
        """Save diagnostic report to file"""
        try:
            report_file = os.path.join(self.test_data_dir, f"diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            
            # Convert dataclass to dict for JSON serialization
            report_dict = {
                "timestamp": report.timestamp,
                "database_health": report.database_health,
                "memory_statistics": report.memory_statistics,
                "retrieval_analysis": report.retrieval_analysis,
                "personality_consistency": report.personality_consistency,
                "temporal_analysis": report.temporal_analysis,
                "recommendations": report.recommendations,
                "critical_issues": report.critical_issues
            }
            
            with open(report_file, 'w') as f:
                json.dump(report_dict, f, indent=2, default=str)
            
            logger.info(f" Diagnostic report saved: {report_file}")
            
        except Exception as e:
            logger.error(f" Failed to save diagnostic report: {e}")
    
    def run_quick_health_check(self) -> Dict:
        """Run quick health check for monitoring"""
        try:
            health_status = {
                "timestamp": datetime.now().isoformat(),
                "status": "healthy",
                "checks": {
                    "sqlite": self._check_sqlite_health(),
                    "chroma": self._check_chroma_health(),
                    "basic_operations": False
                },
                "issues": []
            }
            
            # Test basic operations
            try:
                # Test memory search
                results = self.memory.search_memories("test", n_results=1)
                health_status["checks"]["basic_operations"] = len(results) >= 0  # Empty results are acceptable
            except Exception as e:
                health_status["issues"].append(f"Memory search failed: {e}")
            
            # Determine overall status
            if not all(health_status["checks"].values()):
                health_status["status"] = "unhealthy"
            elif health_status["issues"]:
                health_status["status"] = "degraded"
            
            return health_status
            
        except Exception as e:
            return {
                "timestamp": datetime.now().isoformat(),
                "status": "critical",
                "error": str(e),
                "issues": ["Health check failed entirely"]
            }

def create_diagnostic_tool(memory_system):
    """Create and return a diagnostic tool instance"""
    return MemorySystemDiagnostic(memory_system)