"""
Memory Synchronization Monitor and Diagnostics
Detects and logs memory synchronization failures across the system.
"""
from __future__ import annotations

import asyncio
import time
import sqlite3
import json
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict, deque
import logging
from logger_config import logger

class MemorySyncMonitor:
    def __init__(self, memory_system: Any, background_processor: Any, message_crawler: Any) -> None:
        self.memory = memory_system
        self.bg_processor = background_processor
        self.message_crawler = message_crawler
        
        # Monitoring state
        self.is_monitoring: bool = False
        self.monitor_task: Optional[asyncio.Task[None]] = None
        
        # Failure detection
        self.sync_failures: deque[Dict[str, Any]] = deque(maxlen=1000)
        self.race_condition_signatures: List[str] = []
        self.missing_messages: defaultdict[str, List[Any]] = defaultdict(list)
        self.api_mismatches: List[str] = []
        self.memory_pressure_alerts: List[str] = []
        
        # Performance metrics
        self.snapshot_stats: Dict[str, Any] = {}
        self.operation_times: defaultdict[str, List[float]] = defaultdict(list)
        
        logger.info(" Memory Sync Monitor initialized")
    
    async def start_monitoring(self) -> None:
        """Start continuous synchronization monitoring"""
        if self.is_monitoring:
            logger.warning(" Monitor already running")
            return
        
        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info(" Memory synchronization monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring"""
        self.is_monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
        logger.info(" Memory synchronization monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                await self._run_diagnostics()
                await asyncio.sleep(30)  # Check every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f" Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def _run_diagnostics(self) -> None:
        """Run comprehensive synchronization diagnostics"""
        diagnostics_start = time.time()
        
        # 1. Check API interface mismatches
        await self._check_api_mismatches()
        
        # 2. Monitor database consistency
        await self._check_database_consistency()
        
        # 3. Detect race conditions
        await self._detect_race_conditions()
        
        # 4. Check memory pressure
        await self._check_memory_pressure()
        
        # 5. Verify synchronization gaps
        await self._check_sync_gaps()
        
        # 6. Performance analysis
        self._analyze_performance_metrics(time.time() - diagnostics_start)
    
    async def _check_api_mismatches(self) -> None:
        """Check for API interface mismatches"""
        api_errors = []
        
        # Check background processor queue_message signature
        try:
            import inspect
            sig = inspect.signature(self.bg_processor.queue_message)
            expected_params = set(sig.parameters.keys())
            
            # This is the specific error from logs
            if 'message_id' in expected_params:
                api_errors.append("BackgroundProcessor.queue_message has 'message_id' but shouldn't")
            else:
                logger.debug(" BackgroundProcessor.queue_message signature correct")
        except Exception as e:
            api_errors.append(f"Error checking queue_message signature: {e}")
        
        # Check for other common API issues
        try:
            # Test background processor with expected parameters
            test_data = {
                'content': 'test',
                'user_id': 'test',
                'username': 'test',
                'channel_id': 'test',
                'server_id': 'test',
                'timestamp': datetime.now()
            }
            
            # Test background processor with expected parameters (dry run - check signature only)
            import inspect
            try:
                sig = inspect.signature(self.bg_processor.queue_message)
                expected_params = ['content', 'user_id', 'username', 'channel_id']
                for param in expected_params:
                    if param not in sig.parameters:
                        api_errors.append(f"CRITICAL: queue_message missing parameter '{param}'")
            except (ValueError, TypeError) as e:
                api_errors.append(f"Error inspecting queue_message signature: {e}")
        except Exception as e:
            api_errors.append(f"Error testing queue_message: {e}")
        
        if api_errors:
            self.api_mismatches.extend(api_errors)
            for error in api_errors:
                logger.error(f"🔴 API MISMATCH: {error}")
    
    async def _check_database_consistency(self) -> None:
        """Check consistency between ChromaDB and SQLite"""
        consistency_errors = []
        
        try:
            # Get SQLite stats
            cursor = self.memory.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM recent_messages")
            sqlite_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            sqlite_users = cursor.fetchone()[0]
            
            # Get ChromaDB/Qdrant stats
            if hasattr(self.memory, 'memories'):
                chroma_count = self.memory.memories.count()
            elif hasattr(self.memory, 'get_stats'):
                stats = self.memory.get_stats()
                chroma_count = stats.get('total_memories', 0)
            else:
                chroma_count = 0
            
            # Log the comparison
            if hasattr(self, 'last_db_snapshot'):
                last_sqlite, last_chroma = self.last_db_snapshot
                
                # Check for unexpected drops
                if sqlite_count < last_sqlite * 0.9:  # Dropped more than 10%
                    consistency_errors.append(f"SQLite message count dropped: {last_sqlite} -> {sqlite_count}")
                
                if chroma_count < last_chroma * 0.9:  # Dropped more than 10%
                    consistency_errors.append(f"ChromaDB memory count dropped: {last_chroma} -> {chroma_count}")
            
            self.last_db_snapshot = (sqlite_count, chroma_count)
            
        except Exception as e:
            consistency_errors.append(f"Database consistency check failed: {e}")
        
        if consistency_errors:
            logger.warning(f"🟡 Database consistency issues: {len(consistency_errors)}")
            for error in consistency_errors:
                logger.warning(f"   {error}")
    
    async def _detect_race_conditions(self) -> None:
        """Detect potential race conditions"""
        race_signatures = []
        
        try:
            # Check for concurrent access patterns
            if hasattr(self.bg_processor, 'processing_queue'):
                queue_size = len(self.bg_processor.processing_queue)
                
                # Sudden queue drops might indicate race conditions
                if hasattr(self, 'last_queue_size'):
                    if self.last_queue_size > queue_size and self.last_queue_size - queue_size > 10:
                        race_signatures.append(f"Large queue drop detected: {self.last_queue_size} -> {queue_size}")
                
                self.last_queue_size = queue_size
            
            # Check for rapid sync operations
            if hasattr(self.message_crawler, 'stats'):
                crawler_stats = self.message_crawler.get_stats()
                quick_syncs = crawler_stats.get('quick_syncs', 0)
                
                if hasattr(self, 'last_syncs'):
                    if quick_syncs > self.last_syncs + 3:  # More than 3 sync ops in 30s
                        race_signatures.append(f"Rapid sync operations: {quick_syncs} (last: {self.last_syncs})")
                
                self.last_syncs = quick_syncs
                
        except Exception as e:
            race_signatures.append(f"Error detecting race conditions: {e}")
        
        if race_signatures:
            self.race_condition_signatures.extend(race_signatures)
            logger.warning(f"🟡 Race condition signatures: {race_signatures}")
    
    async def _check_memory_pressure(self) -> None:
        """Check for memory pressure and potential data loss"""
        pressure_alerts = []
        
        try:
            # Check background processor queue
            if hasattr(self.bg_processor, 'processing_queue'):
                queue = self.bg_processor.processing_queue
                queue_size = len(queue)
                max_size = queue.maxlen if hasattr(queue, 'maxlen') else float('inf')
                
                utilization = queue_size / max_size if max_size > 0 else 0
                
                if utilization > 0.9:
                    pressure_alerts.append(f"High queue utilization: {utilization:.1%} ({queue_size}/{max_size})")
                
                # Check for drops
                drops = self.bg_processor.stats.get('queue_drops', 0)
                if hasattr(self, 'last_drops'):
                    new_drops = drops - self.last_drops
                    if new_drops > 0:
                        pressure_alerts.append(f"Queue drops detected: {new_drops} new drops")
                
                self.last_drops = drops
            
            # Check database size growth
            try:
                cursor = self.memory.conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM recent_messages")
                message_count = cursor.fetchone()[0]
                
                if hasattr(self, 'last_message_count'):
                    growth_rate = (message_count - self.last_message_count) / 30  # per second
                    if growth_rate > 100:  # More than 100 messages per second
                        pressure_alerts.append(f"Rapid message growth: {growth_rate:.1f} msg/sec")
                
                self.last_message_count = message_count
                
            except Exception as e:
                pressure_alerts.append(f"Error checking message growth: {e}")
                
        except Exception as e:
            pressure_alerts.append(f"Error checking memory pressure: {e}")
        
        if pressure_alerts:
            self.memory_pressure_alerts.extend(pressure_alerts)
            logger.warning(f"🟡 Memory pressure alerts: {pressure_alerts}")
    
    async def _check_sync_gaps(self) -> None:
        """Check for synchronization gaps between systems"""
        sync_errors = []
        
        try:
            # Check message crawler statistics for gaps
            if hasattr(self.message_crawler, 'stats'):
                stats = self.message_crawler.get_stats()
                
                gaps_found = stats.get('gaps_found', 0)
                if hasattr(self, 'last_gaps'):
                    new_gaps = gaps_found - self.last_gaps
                    if new_gaps > 0:
                        sync_errors.append(f"New synchronization gaps: {new_gaps}")
                
                self.last_gaps = gaps_found
            
            # Check for recently failed sync operations
            recent_errors = [f for f in self.sync_failures if time.time() - f['timestamp'] < 300]
            if recent_errors:
                sync_errors.append(f"{len(recent_errors)} recent sync failures")
                
        except Exception as e:
            sync_errors.append(f"Error checking sync gaps: {e}")
        
        if sync_errors:
            logger.warning(f"🟡 Sync gaps detected: {sync_errors}")
    
    def _analyze_performance_metrics(self, diagnostic_time: float) -> None:
        """Analyze performance and flag slow operations"""
        self.operation_times['diagnostics'].append(diagnostic_time)
        
        # Check if diagnostics are taking too long
        if diagnostic_time > 5.0:  # More than 5 seconds
            logger.warning(f"🟡 Slow diagnostics: {diagnostic_time:.2f}s")
        
        # Check for performance degradation
        if len(self.operation_times['diagnostics']) > 10:
            recent_times = self.operation_times['diagnostics'][-10:]
            avg_time = sum(recent_times) / len(recent_times)
            
            if avg_time > 3.0:
                logger.warning(f"🟡 Performance degradation: avg diagnostics time {avg_time:.2f}s")
    
    def log_sync_failure(self, component: str, operation: str, error: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Log a synchronization failure"""
        failure_record = {
            'timestamp': time.time(),
            'component': component,
            'operation': operation,
            'error': error,
            'context': context or {},
        }
        
        self.sync_failures.append(failure_record)
        logger.exception(f"🔴 SYNC FAILURE [{component}]: {operation} - {error}")
    
    def get_diagnostic_report(self) -> Dict[str, Any]:
        """Get comprehensive diagnostic report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'sync_failures': len(self.sync_failures),
            'api_mismatches': len(self.api_mismatches),
            'race_conditions': len(self.race_condition_signatures),
            'memory_pressure_alerts': len(self.memory_pressure_alerts),
            'recent_failures': [dict(f) for f in list(self.sync_failures)[-10:]],
            'api_issues': self.api_mismatches[-5:],  # Last 5 API issues
            'race_signatures': self.race_condition_signatures[-5:],  # Last 5 race conditions
            'pressure_alerts': self.memory_pressure_alerts[-5:],  # Last 5 pressure alerts
            'system_stats': {
                'bg_queue_size': len(self.bg_processor.processing_queue) if hasattr(self.bg_processor, 'processing_queue') else 0,
                'bg_queue_maxlen': self.bg_processor.processing_queue.maxlen if hasattr(self.bg_processor, 'processing_queue') and hasattr(self.bg_processor.processing_queue, 'maxlen') else 0,
                'bg_queue_drops': self.bg_processor.stats.get('queue_drops', 0) if hasattr(self.bg_processor, 'stats') else 0,
                'crawler_syncs': self.message_crawler.get_stats() if hasattr(self.message_crawler, 'get_stats') else {}
            }
        }
        
        return report
    
    async def force_sync_check(self) -> Dict[str, Any]:
        """Force a comprehensive synchronization check"""
        logger.info(" Running forced synchronization check...")
        
        # Create a temporary detailed snapshot
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'database_state': {},
            'queue_state': {},
            'crawler_state': {},
            'memory_state': {},
            'errors': []
        }
        
        try:
            # Database snapshot
            cursor = self.memory.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM recent_messages")
            snapshot['database_state']['recent_messages'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            snapshot['database_state']['users'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM activity_log")
            snapshot['database_state']['activity_log'] = cursor.fetchone()[0]
            
            # Queue snapshot
            if hasattr(self.bg_processor, 'processing_queue'):
                snapshot['queue_state']['size'] = len(self.bg_processor.processing_queue)
                snapshot['queue_state']['maxlen'] = self.bg_processor.processing_queue.maxlen
                snapshot['queue_state']['stats'] = self.bg_processor.stats.copy()
            
            # Crawler snapshot
            if hasattr(self.message_crawler, 'get_stats'):
                snapshot['crawler_state'] = self.message_crawler.get_stats()
            
            # Memory snapshot
            if hasattr(self.memory, 'get_stats'):
                snapshot['memory_state'] = self.memory.get_stats()
            
        except Exception as e:
            snapshot['errors'].append(f"Snapshot creation failed: {e}")
            logger.error(f" Failed to create sync snapshot: {e}")
        
        logger.info(" Forced synchronization check complete")
        return snapshot