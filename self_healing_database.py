"""
Self-Healing Database Architecture for Memory Systems
Provides automatic detection, diagnosis, and repair of database issues
"""

import sqlite3
import shutil
import json
import os
import hashlib
import tarfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from logger_config import logger

class IssueSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class DatabaseIssue:
    """Represents a detected database issue"""
    severity: IssueSeverity
    category: str
    description: str
    affected_tables: List[str]
    suggested_fix: str
    auto_repairable: bool
    timestamp: str

@dataclass
class RepairAction:
    """Represents a repair action taken"""
    issue_id: str
    action_type: str
    description: str
    timestamp: str
    success: bool
    backup_created: bool
    rollback_data: Dict

class DatabaseIntegrityChecker:
    """Comprehensive database integrity checking and repair"""
    
    def __init__(self, memory_system, backup_dir: str = "./bot_data/backups"):
        self.memory = memory_system
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
        self.issue_registry = {}
        self.repair_history = []
        
    def run_comprehensive_health_check(self) -> Dict:
        """Run comprehensive database health check"""
        logger.info("🔍 Running comprehensive database health check...")
        
        health_report = {
            "timestamp": datetime.now().isoformat(),
            "overall_health_score": 0,
            "checks_performed": [],
            "issues_detected": [],
            "auto_repairs_applied": [],
            "recommendations": []
        }
        
        # Perform all health checks
        checks = [
            self._check_table_integrity,
            self._check_data_consistency,
            self._check_index_performance,
            self._check_backup_status,
            self._check_concurrent_access,
            self._check_corruption_indicators
        ]
        
        total_score = 0
        for check in checks:
            try:
                check_result = check()
                health_report["checks_performed"].append(check_result)
                total_score += check_result.get("score", 0)
            except Exception as e:
                logger.error(f"❌ Health check failed: {e}")
                health_report["checks_performed"].append({
                    "check_name": check.__name__,
                    "error": str(e),
                    "score": 0
                })
        
        health_report["overall_health_score"] = round(total_score / len(checks), 2)
        
        # Detect and categorize issues
        detected_issues = self._detect_issues(health_report)
        health_report["issues_detected"] = detected_issues
        
        # Attempt auto-repairs
        auto_repairs = self._attempt_auto_repairs(detected_issues)
        health_report["auto_repairs_applied"] = auto_repairs
        
        # Generate recommendations
        health_report["recommendations"] = self._generate_health_recommendations(health_report)
        
        # Save health report
        self._save_health_report(health_report)
        
        logger.info(f"✅ Health check completed - Score: {health_report['overall_health_score']}/100")
        return health_report
    
    def _check_table_integrity(self) -> Dict:
        """Check database table integrity"""
        logger.debug("🗄️ Checking table integrity...")
        
        result = {
            "check_name": "table_integrity",
            "score": 100,
            "details": {},
            "issues": []
        }
        
        try:
            cursor = self.memory.conn.cursor()
            
            # Check required tables exist
            required_tables = ['users', 'relationships', 'activity_log', 'recent_messages']
            for table in required_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                result["details"][table] = {"exists": True, "record_count": count}
                
                # Check table structure
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cursor.fetchall()]
                result["details"][table]["columns"] = columns
                
                # Check for common integrity issues
                integrity_issues = self._check_single_table_integrity(table)
                if integrity_issues:
                    result["issues"].extend(integrity_issues)
                    result["score"] -= len(integrity_issues) * 5
            
            # Check foreign key constraints
            cursor.execute("PRAGMA foreign_key_check")
            fk_violations = cursor.fetchall()
            if fk_violations:
                result["issues"].append({
                    "type": "foreign_key_violations",
                    "count": len(fk_violations),
                    "details": fk_violations[:5]  # First 5 violations
                })
                result["score"] -= len(fk_violations) * 3
            
            # Check for table corruption
            cursor.execute("PRAGMA integrity_check")
            integrity_check = cursor.fetchall()
            if integrity_check and integrity_check[0][0] != "ok":
                result["issues"].append({
                    "type": "table_corruption",
                    "details": integrity_check
                })
                result["score"] -= 20
            
        except Exception as e:
            logger.error(f"❌ Table integrity check failed: {e}")
            result["error"] = str(e)
            result["score"] = 0
        
        return result
    
    def _check_single_table_integrity(self, table_name: str) -> List[Dict]:
        """Check integrity of a single table"""
        issues = []
        cursor = self.memory.conn.cursor()
        
        try:
            if table_name == "users":
                # Check for duplicate user_ids
                cursor.execute("""
                    SELECT user_id, COUNT(*) 
                    FROM users 
                    GROUP BY user_id 
                    HAVING COUNT(*) > 1
                """)
                duplicates = cursor.fetchall()
                if duplicates:
                    issues.append({
                        "table": table_name,
                        "type": "duplicate_user_ids",
                        "count": len(duplicates),
                        "details": [str(d) for d in duplicates[:3]]
                    })
                
                # Check for NULL required fields
                cursor.execute("""
                    SELECT COUNT(*) FROM users 
                    WHERE user_id IS NULL OR username IS NULL
                """)
                null_count = cursor.fetchone()[0]
                if null_count > 0:
                    issues.append({
                        "table": table_name,
                        "type": "null_required_fields",
                        "count": null_count
                    })
            
            elif table_name == "relationships":
                # Check for invalid relationship strengths
                cursor.execute("""
                    SELECT COUNT(*) FROM relationships 
                    WHERE relationship_strength < 0 OR relationship_strength > 1
                """)
                invalid_strength = cursor.fetchone()[0]
                if invalid_strength > 0:
                    issues.append({
                        "table": table_name,
                        "type": "invalid_relationship_strength",
                        "count": invalid_strength
                    })
            
            elif table_name == "recent_messages":
                # Check for orphaned messages (user doesn't exist)
                cursor.execute("""
                    SELECT COUNT(*) FROM recent_messages rm
                    LEFT JOIN users u ON rm.user_id = u.user_id
                    WHERE u.user_id IS NULL
                """)
                orphaned = cursor.fetchone()[0]
                if orphaned > 0:
                    issues.append({
                        "table": table_name,
                        "type": "orphaned_messages",
                        "count": orphaned
                    })
                
                # Check for duplicate message_ids
                cursor.execute("""
                    SELECT message_id, COUNT(*) 
                    FROM recent_messages 
                    GROUP BY message_id 
                    HAVING COUNT(*) > 1
                """)
                duplicates = cursor.fetchall()
                if duplicates:
                    issues.append({
                        "table": table_name,
                        "type": "duplicate_message_ids",
                        "count": len(duplicates)
                    })
        
        except Exception as e:
            logger.error(f"❌ Single table integrity check failed for {table_name}: {e}")
            issues.append({
                "table": table_name,
                "type": "check_failed",
                "error": str(e)
            })
        
        return issues
    
    def _check_data_consistency(self) -> Dict:
        """Check data consistency across tables"""
        logger.debug("🔄 Checking data consistency...")
        
        result = {
            "check_name": "data_consistency",
            "score": 100,
            "details": {},
            "issues": []
        }
        
        try:
            cursor = self.memory.conn.cursor()
            
            # Check user-message consistency
            cursor.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM users) as total_users,
                    (SELECT COUNT(DISTINCT user_id) FROM recent_messages) as users_with_messages,
                    (SELECT COUNT(*) FROM recent_messages WHERE user_id NOT IN (SELECT user_id FROM users)) as orphaned_messages
            """)
            
            user_stats = cursor.fetchone()
            total_users = user_stats[0]
            users_with_messages = user_stats[1]
            orphaned_messages = user_stats[2]
            
            result["details"]["user_message_consistency"] = {
                "total_users": total_users,
                "users_with_messages": users_with_messages,
                "orphaned_messages": orphaned_messages,
                "consistency_ratio": round(users_with_messages / max(1, total_users), 3)
            }
            
            # Calculate consistency score
            if orphaned_messages > 0:
                result["score"] -= min(30, orphaned_messages * 2)
            
            if total_users > 0 and users_with_messages / total_users < 0.5:
                result["score"] -= 20
            
            # Check relationship consistency
            cursor.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM relationships WHERE user_a_id NOT IN (SELECT user_id FROM users)) as invalid_user_a,
                    (SELECT COUNT(*) FROM relationships WHERE user_b_id NOT IN (SELECT user_id FROM users)) as invalid_user_b
            """)
            
            rel_stats = cursor.fetchone()
            invalid_user_a = rel_stats[0]
            invalid_user_b = rel_stats[1]
            
            if invalid_user_a > 0 or invalid_user_b > 0:
                result["issues"].append({
                    "type": "invalid_relationship_users",
                    "invalid_user_a": invalid_user_a,
                    "invalid_user_b": invalid_user_b
                })
                result["score"] -= (invalid_user_a + invalid_user_b) * 5
            
        except Exception as e:
            logger.error(f"❌ Data consistency check failed: {e}")
            result["error"] = str(e)
            result["score"] = 0
        
        return result
    
    def _check_index_performance(self) -> Dict:
        """Check index performance and suggest optimizations"""
        logger.debug("📊 Checking index performance...")
        
        result = {
            "check_name": "index_performance",
            "score": 80,  # Default reasonable score
            "details": {},
            "recommendations": []
        }
        
        try:
            cursor = self.memory.conn.cursor()
            
            # Check existing indexes
            cursor.execute("PRAGMA index_list('recent_messages')")
            indexes = cursor.fetchall()
            existing_indexes = [idx[1] for idx in indexes]
            
            result["details"]["existing_indexes"] = existing_indexes
            
            # Suggest missing indexes
            recommended_indexes = [
                ("idx_recent_messages_user_time", "recent_messages(user_id, timestamp DESC)"),
                ("idx_recent_messages_channel_time", "recent_messages(channel_id, timestamp DESC)"),
                ("idx_relationships_strength", "relationships(relationship_strength DESC)"),
                ("idx_users_last_seen", "users(last_seen DESC)")
            ]
            
            missing_indexes = []
            for idx_name, idx_sql in recommended_indexes:
                if idx_name not in existing_indexes:
                    missing_indexes.append({
                        "name": idx_name,
                        "sql": f"CREATE INDEX {idx_name} ON {idx_sql}"
                    })
                    result["recommendations"].append(f"Consider creating index: {idx_name}")
            
            result["details"]["missing_indexes"] = missing_indexes
            result["score"] -= len(missing_indexes) * 3  # Penalty for missing indexes
            
        except Exception as e:
            logger.error(f"❌ Index performance check failed: {e}")
            result["error"] = str(e)
            result["score"] = 50  # Reduced score for failed check
        
        return result
    
    def _check_backup_status(self) -> Dict:
        """Check backup system status"""
        logger.debug("💾 Checking backup status...")
        
        result = {
            "check_name": "backup_status",
            "score": 80,
            "details": {},
            "issues": []
        }
        
        try:
            # Check backup directory exists
            if not os.path.exists(self.backup_dir):
                result["issues"].append("Backup directory does not exist")
                result["score"] -= 50
                return result
            
            # Check recent backups
            backup_files = [f for f in os.listdir(self.backup_dir) if f.endswith('.tar.gz')]
            recent_backups = []
            now = datetime.now()
            
            for backup_file in backup_files:
                backup_path = os.path.join(self.backup_dir, backup_file)
                if os.path.exists(backup_path):
                    mtime = datetime.fromtimestamp(os.path.getmtime(backup_path))
                    if (now - mtime).days < 1:
                        recent_backups.append(backup_file)
            
            result["details"] = {
                "total_backups": len(backup_files),
                "recent_backups": recent_backups,
                "backup_freshness": "good" if recent_backups else "concerning"
            }
            
            if not recent_backups:
                result["issues"].append("No recent backups found")
                result["score"] -= 20
            
            # Check backup file integrity (sample)
            if backup_files:
                sample_backup = os.path.join(self.backup_dir, backup_files[-1])
                try:
                    with tarfile.open(sample_backup, 'r:gz') as tar:
                        tar.getmembers()  # Just test if it opens without error
                except Exception:
                    result["issues"].append(f"Backup file appears corrupted: {backup_files[-1]}")
                    result["score"] -= 30
            
        except Exception as e:
            logger.error(f"❌ Backup status check failed: {e}")
            result["error"] = str(e)
            result["score"] = 40
        
        return result
    
    def _check_concurrent_access(self) -> Dict:
        """Check for concurrent access issues"""
        logger.debug("🔄 Checking concurrent access...")
        
        result = {
            "check_name": "concurrent_access",
            "score": 90,
            "details": {},
            "issues": []
        }
        
        try:
            # Check SQLite WAL mode status
            cursor = self.memory.conn.cursor()
            cursor.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
            
            result["details"]["journal_mode"] = journal_mode
            
            if journal_mode.lower() != 'wal':
                result["issues"].append("Database not using WAL mode - may have concurrency issues")
                result["score"] -= 10
            
            # Check for active transactions
            cursor.execute("PRAGMA database_list")
            db_list = cursor.fetchall()
            
            if len(db_list) > 1:
                result["details"]["active_connections"] = len(db_list)
                result["score"] -= 5  # Penalty for multiple connections
            
        except Exception as e:
            logger.error(f"❌ Concurrent access check failed: {e}")
            result["error"] = str(e)
            result["score"] = 70
        
        return result
    
    def _check_corruption_indicators(self) -> Dict:
        """Check for database corruption indicators"""
        logger.debug("🚨 Checking corruption indicators...")
        
        result = {
            "check_name": "corruption_indicators",
            "score": 100,
            "details": {},
            "issues": []
        }
        
        try:
            cursor = self.memory.conn.cursor()
            
            # Check SQLite integrity
            cursor.execute("PRAGMA quick_check")
            quick_check = cursor.fetchall()
            
            if quick_check and quick_check[0][0] != "ok":
                result["issues"].append({
                    "type": "integrity_check_failed",
                    "details": quick_check
                })
                result["score"] -= 50
            
            # Check for unusual table sizes
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            
            tables = cursor.fetchall()
            for (table_name,) in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    result["details"][f"{table_name}_count"] = count
                    
                    # Flag unusually high counts (potential corruption indicator)
                    if count > 1000000:  # Arbitrary threshold
                        result["issues"].append({
                            "type": "unusually_high_count",
                            "table": table_name,
                            "count": count
                        })
                        result["score"] -= 10
                
                except Exception as e:
                    result["issues"].append({
                        "type": "table_access_error",
                        "table": table_name,
                        "error": str(e)
                    })
                    result["score"] -= 5
            
            # Check ChromaDB health
            try:
                chroma_count = self.memory.memories.count()
                result["details"]["chroma_memories"] = chroma_count
                
                # Flag unusually high memory counts
                if chroma_count > 500000:
                    result["issues"].append({
                        "type": "high_memory_count",
                        "count": chroma_count
                    })
                    result["score"] -= 15
                    
            except Exception as e:
                result["issues"].append({
                    "type": "chroma_access_error",
                    "error": str(e)
                })
                result["score"] -= 30
        
        except Exception as e:
            logger.error(f"❌ Corruption indicators check failed: {e}")
            result["error"] = str(e)
            result["score"] = 50
        
        return result
    
    def _detect_issues(self, health_report: Dict) -> List[DatabaseIssue]:
        """Detect database issues from health report"""
        issues = []
        
        for check in health_report["checks_performed"]:
            check_name = check.get("check_name", "")
            check_issues = check.get("issues", [])
            
            for issue_data in check_issues:
                severity = IssueSeverity.LOW
                
                # Determine severity based on issue type and details
                if "corruption" in str(issue_data).lower():
                    severity = IssueSeverity.CRITICAL
                elif "integrity" in str(issue_data).lower():
                    severity = IssueSeverity.HIGH
                elif "orphan" in str(issue_data).lower():
                    severity = IssueSeverity.MEDIUM
                elif check.get("score", 100) < 70:
                    severity = IssueSeverity.MEDIUM
                
                issue = DatabaseIssue(
                    severity=severity,
                    category=check_name,
                    description=str(issue_data),
                    affected_tables=issue_data.get("table", []) if isinstance(issue_data, dict) else [],
                    suggested_fix=self._generate_fix_suggestion(issue_data),
                    auto_repairable=self._is_auto_repairable(issue_data),
                    timestamp=datetime.now().isoformat()
                )
                
                issues.append(issue)
        
        return issues
    
    def _generate_fix_suggestion(self, issue_data: Dict) -> str:
        """Generate fix suggestion for an issue"""
        issue_type = issue_data.get("type", "")
        
        fix_suggestions = {
            "duplicate_user_ids": "Remove duplicate user records, keeping the most recent",
            "orphaned_messages": "Delete orphaned messages or create missing user records",
            "foreign_key_violations": "Fix referential integrity constraints",
            "invalid_relationship_strength": "Normalize relationship strength values to 0-1 range",
            "table_corruption": "Restore from backup or rebuild table",
            "high_memory_count": "Implement memory archival or cleanup strategy"
        }
        
        return fix_suggestions.get(issue_type, "Manual investigation required")
    
    def _is_auto_repairable(self, issue_data: Dict) -> bool:
        """Determine if an issue can be auto-repaired"""
        auto_repairable_types = [
            "duplicate_user_ids",
            "orphaned_messages", 
            "invalid_relationship_strength",
            "missing_indexes"
        ]
        
        return issue_data.get("type", "") in auto_repairable_types
    
    def _attempt_auto_repairs(self, issues: List[DatabaseIssue]) -> List[RepairAction]:
        """Attempt to automatically repair issues"""
        logger.info("🔧 Attempting auto-repairs...")
        
        repairs = []
        
        for issue in issues:
            if not issue.auto_repairable:
                continue
            
            try:
                repair_action = self._repair_issue(issue)
                if repair_action:
                    repairs.append(repair_action)
                    
            except Exception as e:
                logger.error(f"❌ Auto-repair failed for {issue.category}: {e}")
                repairs.append(RepairAction(
                    issue_id=str(hash(str(issue))),
                    action_type="repair_attempt",
                    description=f"Failed to repair: {e}",
                    timestamp=datetime.now().isoformat(),
                    success=False,
                    backup_created=False,
                    rollback_data={}
                ))
        
        return repairs
    
    def _repair_issue(self, issue: DatabaseIssue) -> Optional[RepairAction]:
        """Attempt to repair a specific issue"""
        logger.info(f"🔧 Attempting to repair: {issue.description}")
        
        # Create backup before repair
        backup_path = self._create_pre_repair_backup()
        rollback_data = {}
        
        try:
            cursor = self.memory.conn.cursor()
            
            if "duplicate_user_ids" in issue.description:
                # Remove duplicate users, keep the most recent
                cursor.execute("""
                    DELETE FROM users 
                    WHERE rowid NOT IN (
                        SELECT MAX(rowid) 
                        FROM users 
                        GROUP BY user_id
                    )
                """)
                affected_count = cursor.rowcount
                
                rollback_data["deleted_users"] = affected_count
                self.memory.conn.commit()
                
                logger.info(f"✅ Removed {affected_count} duplicate users")
                
            elif "orphaned_messages" in issue.description:
                # Delete orphaned messages
                cursor.execute("""
                    DELETE FROM recent_messages 
                    WHERE user_id NOT IN (SELECT user_id FROM users)
                """)
                affected_count = cursor.rowcount
                
                rollback_data["deleted_messages"] = affected_count
                self.memory.conn.commit()
                
                logger.info(f"✅ Removed {affected_count} orphaned messages")
                
            elif "invalid_relationship_strength" in issue.description:
                # Fix invalid relationship strengths
                cursor.execute("""
                    UPDATE relationships 
                    SET relationship_strength = ABS(relationship_strength % 1.0)
                    WHERE relationship_strength < 0 OR relationship_strength > 1
                """)
                affected_count = cursor.rowcount
                
                rollback_data["fixed_strengths"] = affected_count
                self.memory.conn.commit()
                
                logger.info(f"✅ Fixed {affected_count} invalid relationship strengths")
            
            else:
                logger.warning(f"⚠️ No auto-repair implemented for: {issue.category}")
                return None
            
            return RepairAction(
                issue_id=str(hash(str(issue))),
                action_type="auto_repair",
                description=f"Successfully repaired: {issue.category}",
                timestamp=datetime.now().isoformat(),
                success=True,
                backup_created=bool(backup_path),
                rollback_data=rollback_data
            )
            
        except Exception as e:
            logger.error(f"❌ Auto-repair failed: {e}")
            return RepairAction(
                issue_id=str(hash(str(issue))),
                action_type="auto_repair",
                description=f"Failed: {e}",
                timestamp=datetime.now().isoformat(),
                success=False,
                backup_created=bool(backup_path),
                rollback_data={}
            )
    
    def _create_pre_repair_backup(self) -> Optional[str]:
        """Create backup before repair operation"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"pre_repair_{timestamp}.tar.gz"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Create database backup
            db_backup_path = os.path.join(self.backup_dir, f"bot_data_pre_repair_{timestamp}.db")
            shutil.copy2(self.memory.db_path, db_backup_path)
            
            # Create ChromaDB backup
            chroma_backup_path = os.path.join(self.backup_dir, f"chroma_data_pre_repair_{timestamp}.tar.gz")
            if os.path.exists(self.memory.data_dir):
                with tarfile.open(chroma_backup_path, 'w:gz') as tar:
                    tar.add(self.memory.data_dir, arcname='chroma_data')
            
            # Create combined backup
            with tarfile.open(backup_path, 'w:gz') as tar:
                tar.add(db_backup_path, arcname='bot_data.db')
                tar.add(chroma_backup_path, arcname='chroma_data.tar.gz')
            
            # Clean up individual files
            os.remove(db_backup_path)
            os.remove(chroma_backup_path)
            
            logger.info(f"💾 Pre-repair backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ Failed to create pre-repair backup: {e}")
            return None
    
    def _generate_health_recommendations(self, health_report: Dict) -> List[str]:
        """Generate health recommendations based on report"""
        recommendations = []
        
        score = health_report["overall_health_score"]
        issues = health_report["issues_detected"]
        
        if score < 50:
            recommendations.append("🚨 Critical: Immediate attention required for database health")
        elif score < 70:
            recommendations.append("⚠️ Database health needs improvement")
        elif score < 85:
            recommendations.append("💡 Consider optimizations for better performance")
        else:
            recommendations.append("✅ Database health is good")
        
        # Specific recommendations based on issues
        issue_types = [issue.category for issue in issues]
        
        if "table_integrity" in issue_types:
            recommendations.append("Review table integrity issues and consider schema optimization")
        
        if "backup_status" in issue_types:
            recommendations.append("Improve backup strategy with more frequent automated backups")
        
        if "index_performance" in issue_types:
            recommendations.append("Create missing indexes for better query performance")
        
        if "corruption_indicators" in issue_types:
            recommendations.append("Investigate corruption indicators and consider preventive measures")
        
        return recommendations
    
    def _save_health_report(self, health_report: Dict):
        """Save health report to file"""
        try:
            report_file = os.path.join(self.backup_dir, f"health_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            
            with open(report_file, 'w') as f:
                json.dump(health_report, f, indent=2, default=str)
            
            logger.info(f"💾 Health report saved: {report_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save health report: {e}")
    
    def create_emergency_backup(self) -> Optional[str]:
        """Create emergency backup of current database state"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"emergency_backup_{timestamp}.tar.gz"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Create complete backup
            with tarfile.open(backup_path, 'w:gz') as tar:
                # Add database
                tar.add(self.memory.db_path, arcname='bot_data.db')
                
                # Add ChromaDB data
                if os.path.exists(self.memory.data_dir):
                    tar.add(self.memory.data_dir, arcname='chroma_data')
                
                # Add backup metadata
                metadata = {
                    "timestamp": timestamp,
                    "type": "emergency_backup",
                    "reason": "Manual emergency backup",
                    "database_size": os.path.getsize(self.memory.db_path)
                }
                
                metadata_file = os.path.join(os.path.dirname(backup_path), f"backup_info.json")
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
                
                tar.add(metadata_file, arcname='backup_info.json')
            
            logger.info(f"🚨 Emergency backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ Emergency backup failed: {e}")
            return None

def create_database_healer(memory_system):
    """Create database integrity checker and repair system"""
    return DatabaseIntegrityChecker(memory_system)