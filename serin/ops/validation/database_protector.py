"""
Production-Grade Database Protection System
Prevents and handles database corruption in production environments.

Features:
- Pre-startup integrity validation
- Automatic backup with versioning
- Graceful recovery from corruption
- Clean shutdown handlers
- Health monitoring
"""
import os
import shutil
import sqlite3
import time
import gzip
import json
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import Dict, List, Optional, Tuple
from serin.state.logger import logger

class DatabaseValidationError(Exception):
    """Raised when database validation fails"""
    pass

class DatabaseRecoveryError(Exception):
    """Raised when database recovery fails"""
    pass

class DatabaseProtector:
    def __init__(self, data_dir: str = "./bot_data", backup_dir: Optional[str] = None) -> None:
        """
        Initialize database protection system
        
        Args:
            data_dir: Main database directory
            backup_dir: Custom backup directory (defaults to data_dir/backups)
        """
        self.data_dir = Path(data_dir)
        self.backup_dir = Path(backup_dir) if backup_dir else self.data_dir / "backups"
        # Ensure backup_dir is always a Path object
        if not isinstance(self.backup_dir, Path):
            self.backup_dir = Path(self.backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration
        self.max_backups = 50  # Keep up to 50 backups
        self.backup_interval = 3600  # 1 hour between automatic backups
        self.validation_enabled = True
        
        # Database paths
        self.chroma_dir = self.data_dir / "chroma_data"
        self.sqlite_db = self.data_dir / "bot_data.db"
        
        # State tracking
        self.last_backup_time = 0
        self.backup_count = 0
        self.validation_failures = []
        
        logger.info(" Database Protection System initialized")
        logger.info(f"   📁 Data directory: {self.data_dir}")
        logger.info(f"    Backup directory: {self.backup_dir}")
        logger.info(f"    Validation: {'ENABLED' if self.validation_enabled else 'DISABLED'}")

    # ========================================================================
    # DATABASE VALIDATION
    # ========================================================================
    
    def validate_all_databases(self) -> Dict:
        """
        Comprehensive database validation before startup
        
        Returns:
            Dict with validation results
        """
        validation_start = time.time()
        results = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'unknown',
            'sqlite_validation': {},
            'chroma_validation': {},
            'validation_time': 0,
            'errors': [],
            'warnings': []
        }
        
        try:
            logger.info(" Starting comprehensive database validation...")
            
            # Validate SQLite database
            sqlite_results = self._validate_sqlite_database()
            results['sqlite_validation'] = sqlite_results
            
            if not sqlite_results['valid']:
                results['errors'].append(f"SQLite validation failed: {sqlite_results['error']}")
            
            # Validate ChromaDB database
            chroma_results = self._validate_chroma_database()
            results['chroma_validation'] = chroma_results
            
            if not chroma_results['valid']:
                results['errors'].append(f"ChromaDB validation failed: {chroma_results['error']}")
            
            # Determine overall status - be more lenient for empty databases
            # Check if all errors are just "does not exist", "missing files", or "Missing required tables"
            all_missing = all(
                'does not exist' in err or 'missing files' in err or 'Missing required tables' in err
                for err in results['errors']
            )
            
            if not results['errors']:
                results['overall_status'] = 'valid'
                logger.info(" Database validation PASSED")
            elif all_missing:
                # Allow empty databases to start fresh (even if multiple are missing)
                results['overall_status'] = 'valid'
                logger.info(" Database validation PASSED (fresh start - databases will be created)")
            elif len(results['errors']) == 1:
                results['overall_status'] = 'recoverable'
                logger.warning(" Database validation found recoverable issues")
            else:
                results['overall_status'] = 'critical'
                logger.error(" Database validation FAILED - critical errors found")
            
            results['validation_time'] = time.time() - validation_start
            
        except Exception as e:
            results['overall_status'] = 'error'
            results['errors'].append(f"Validation error: {str(e)}")
            logger.error(f" Database validation error: {e}")
        
        return results
    
    def _validate_sqlite_database(self) -> Dict:
        """Validate SQLite database integrity"""
        results = {
            'valid': False,
            'exists': False,
            'readable': False,
            'writable': False,
            'schema_valid': False,
            'integrity_check': False,
            'error': None,
            'file_size': 0,
            'page_count': 0
        }
        
        try:
            if not self.sqlite_db.exists():
                results['error'] = "SQLite database does not exist"
                return results
            
            results['exists'] = True
            results['file_size'] = self.sqlite_db.stat().st_size
            
            # Test read/write access
            try:
                with open(self.sqlite_db, 'rb') as f:
                    f.read(1024)  # Read first 1KB
                results['readable'] = True
            except Exception as e:
                results['error'] = f"Cannot read database: {e}"
                return results
            
            # Check SQLite integrity
            conn = sqlite3.connect(str(self.sqlite_db))
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                integrity_result = cursor.fetchone()[0]
                
                if integrity_result == "ok":
                    results['integrity_check'] = True
                else:
                    results['error'] = f"SQLite integrity check failed: {integrity_result}"
                    return results
                
                # Get page count
                cursor.execute("PRAGMA page_count;")
                results['page_count'] = cursor.fetchone()[0]
                
                # Check critical tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                tables = [row[0] for row in cursor.fetchall()]
                
                required_tables = ['users', 'relationships', 'recent_messages']
                missing_tables = [t for t in required_tables if t not in tables]
                
                # For empty/new databases, missing tables are acceptable
                if missing_tables and len(tables) > 1:  # More than just sqlite system tables
                    results['error'] = f"Missing required tables: {missing_tables}"
                else:
                    results['schema_valid'] = True
                    results['valid'] = True
                
            finally:
                conn.close()
                
        except Exception as e:
            results['error'] = f"SQLite validation error: {e}"
        
        return results
    
    def _validate_chroma_database(self) -> Dict:
        """Validate ChromaDB database structure"""
        results = {
            'valid': False,
            'directory_exists': False,
            'sqlite_component_valid': False,
            'binary_files_valid': False,
            'error': None,
            'file_sizes': {},
            'missing_files': []
        }
        
        try:
            if not self.chroma_dir.exists():
                results['error'] = "ChromaDB directory does not exist"
                return results
            
            results['directory_exists'] = True
            
            # Check SQLite component
            sqlite_path = self.chroma_dir / "chroma.sqlite3"
            if sqlite_path.exists():
                results['sqlite_component_valid'] = True
                results['file_sizes']['sqlite'] = sqlite_path.stat().st_size
            else:
                results['missing_files'].append('chroma.sqlite3')
            
            # Check binary files directory
            for subdir in self.chroma_dir.iterdir():
                if subdir.is_dir():
                    # Check required binary files
                    required_files = ['header.bin', 'length.bin', 'link_lists.bin', 'data_level0.bin']
                    
                    for req_file in required_files:
                        file_path = subdir / req_file
                        if file_path.exists():
                            results['file_sizes'][f"{subdir.name}/{req_file}"] = file_path.stat().st_size
                            
                            # Check for empty/corrupted files
                            if req_file == 'link_lists.bin' and file_path.stat().st_size == 0:
                                results['binary_files_valid'] = False
                                results['error'] = f"Empty binary file: {req_file}"
                                return results
                        else:
                            results['missing_files'].append(f"{subdir.name}/{req_file}")
            
            # Determine validity
            if results['missing_files']:
                if len(results['missing_files']) > 2:
                    results['error'] = f"Too many missing files: {results['missing_files']}"
                else:
                    results['valid'] = True  # Some files can be regenerated
            else:
                results['binary_files_valid'] = True
                results['valid'] = True
            
        except Exception as e:
            results['error'] = f"ChromaDB validation error: {e}"
        
        return results
    
    # ========================================================================
    # BACKUP SYSTEM
    # ========================================================================
    