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
from logger_config import logger

class DatabaseValidationError(Exception):
    """Raised when database validation fails"""
    pass

class DatabaseRecoveryError(Exception):
    """Raised when database recovery fails"""
    pass

class DatabaseProtector:
    def __init__(self, data_dir: str = "./bot_data", backup_dir: str = None):
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
        
        logger.info("🛡️ Database Protection System initialized")
        logger.info(f"   📁 Data directory: {self.data_dir}")
        logger.info(f"   💾 Backup directory: {self.backup_dir}")
        logger.info(f"   🔍 Validation: {'ENABLED' if self.validation_enabled else 'DISABLED'}")

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
            logger.info("🔍 Starting comprehensive database validation...")
            
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
            if not results['errors']:
                results['overall_status'] = 'valid'
                logger.info("✅ Database validation PASSED")
            elif len(results['errors']) == 1 and 'does not exist' in results['errors'][0]:
                # Allow empty databases to start fresh
                results['overall_status'] = 'valid'
                logger.info("✅ Database validation PASSED (empty databases will be created)")
            elif len(results['errors']) == 1:
                results['overall_status'] = 'recoverable'
                logger.warning("⚠️ Database validation found recoverable issues")
            else:
                results['overall_status'] = 'critical'
                logger.error("❌ Database validation FAILED - critical errors found")
            
            results['validation_time'] = time.time() - validation_start
            
        except Exception as e:
            results['overall_status'] = 'error'
            results['errors'].append(f"Validation error: {str(e)}")
            logger.error(f"❌ Database validation error: {e}")
        
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
    
    def create_backup(self, backup_type: str = "manual", force: bool = False) -> str:
        """
        Create timestamped backup of all databases
        
        Args:
            backup_type: Type of backup ("manual", "automatic", "pre_shutdown")
            force: Force backup even if not due
        
        Returns:
            Path to created backup directory
        """
        try:
            current_time = time.time()
            
            # Check if automatic backup is due
            if backup_type == "automatic" and not force:
                if current_time - self.last_backup_time < self.backup_interval:
                    logger.debug(f"Skipping automatic backup (last: {current_time - self.last_backup_time}s ago)")
                    return ""
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{backup_type}_{timestamp}"
            backup_path = self.backup_dir / backup_name
            
            logger.info(f"💾 Creating {backup_type} backup: {backup_name}")
            
            # Create backup directory
            backup_path.mkdir(parents=True, exist_ok=True)
            
            backup_info = {
                'backup_type': backup_type,
                'timestamp': timestamp,
                'created_at': datetime.now().isoformat(),
                'bot_version': 'unknown',  # Could be enhanced with actual version
                'databases_backed_up': [],
                'errors': []
            }
            
            # Backup SQLite database
            if self.sqlite_db.exists():
                try:
                    backup_sqlite = backup_path / "bot_data.db"
                    shutil.copy2(self.sqlite_db, backup_sqlite)
                    backup_info['databases_backed_up'].append('SQLite')
                    logger.debug("✅ SQLite database backed up")
                except Exception as e:
                    backup_info['errors'].append(f"SQLite backup error: {e}")
                    logger.error(f"❌ SQLite backup failed: {e}")
            
            # Backup ChromaDB directory
            if self.chroma_dir.exists():
                try:
                    backup_chroma = backup_path / "chroma_data"
                    shutil.copytree(self.chroma_dir, backup_chroma)
                    backup_info['databases_backed_up'].append('ChromaDB')
                    logger.debug("✅ ChromaDB directory backed up")
                except Exception as e:
                    backup_info['errors'].append(f"ChromaDB backup error: {e}")
                    logger.error(f"❌ ChromaDB backup failed: {e}")
            
            # Save backup metadata
            metadata_file = backup_path / "backup_info.json"
            with open(metadata_file, 'w') as f:
                json.dump(backup_info, f, indent=2)
            
            # Compress backup if it contains data
            if backup_info['databases_backed_up']:
                self._compress_backup(backup_path)
                self.backup_count += 1
                self.last_backup_time = current_time
                
                # Clean up old backups
                self._cleanup_old_backups()
                
                logger.info(f"✅ {backup_type} backup completed: {backup_name}")
                return str(backup_path)
            else:
                # Remove empty backup directory
                shutil.rmtree(backup_path)
                logger.warning(f"⚠️ {backup_type} backup failed - no databases backed up")
                return ""
                
        except Exception as e:
            logger.error(f"❌ Backup creation failed: {e}")
            raise DatabaseRecoveryError(f"Backup creation failed: {e}")
    
    def _compress_backup(self, backup_path: Path):
        """Compress backup directory to save space"""
        try:
            # Create tar.gz archive with correct parameters
            shutil.make_archive(
                str(backup_path.with_suffix('')),  # Output filename (without .tar.gz)
                'gztar',  # Format
                root_dir=str(backup_path.parent),  # Root directory
                base_dir=backup_path.name  # Directory to archive (just the folder name)
            )
            
            # Remove uncompressed directory
            shutil.rmtree(backup_path)
            
            logger.debug(f"✅ Backup compressed successfully")
            
        except Exception as e:
            logger.warning(f"⚠️ Backup compression failed: {e}")
            # Don't fail the backup process if compression fails
            logger.info(f"✅ Backup completed without compression: {backup_path.name}")
    
    def _cleanup_old_backups(self):
        """Remove old backups beyond retention limit"""
        try:
            backup_files = list(self.backup_dir.glob("*.tar.gz"))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove excess backups
            for backup_file in backup_files[self.max_backups:]:
                backup_file.unlink()
                logger.debug(f"🗑️ Removed old backup: {backup_file.name}")
            
            # Also check for uncompressed backup directories
            for backup_dir in self.backup_dir.iterdir():
                if backup_dir.is_dir():
                    backup_files.append(backup_dir)
            
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove excess directories
            for backup_item in backup_files[self.max_backups:]:
                if backup_item.is_dir():
                    shutil.rmtree(backup_item)
                else:
                    backup_item.unlink()
                logger.debug(f"🗑️ Removed old backup: {backup_item.name}")
                
        except Exception as e:
            logger.warning(f"⚠️ Backup cleanup failed: {e}")
    
    def list_backups(self) -> List[Dict]:
        """List all available backups with metadata"""
        backups = []
        
        try:
            # Check compressed backups
            for backup_file in self.backup_dir.glob("*.tar.gz"):
                try:
                    backup_info = self._extract_and_validate_backup_metadata(backup_file)
                    if backup_info:
                        backups.append(backup_info)
                except Exception as e:
                    logger.warning(f"⚠️ Could not read backup info: {e}")
            
            # Check uncompressed directories
            for backup_dir in self.backup_dir.iterdir():
                if backup_dir.is_dir():
                    metadata_file = backup_dir / "backup_info.json"
                    if metadata_file.exists():
                        try:
                            with open(metadata_file) as f:
                                backup_info = json.load(f)
                            backup_info['path'] = str(backup_dir)
                            backup_info['compressed'] = False
                            backups.append(backup_info)
                        except Exception as e:
                            logger.warning(f"⚠️ Could not read backup metadata: {e}")
            
            # Sort by creation time
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            
        except Exception as e:
            logger.error(f"❌ Error listing backups: {e}")
        
        return backups
    
    def _extract_and_validate_backup_metadata(self, backup_file: Path) -> Optional[Dict]:
        """
        Extract and validate backup metadata from compressed backup archive.
        
        Args:
            backup_file: Path to compressed backup file (.tar.gz)
            
        Returns:
            Dictionary containing backup metadata if successful, None otherwise
            
        Raises:
            FileNotFoundError: If backup file does not exist
            PermissionError: If backup file cannot be read
            json.JSONDecodeError: If metadata file contains invalid JSON
            UnicodeDecodeError: If metadata file cannot be decoded as UTF-8
        """
        if not backup_file.exists():
            logger.error(f"❌ Backup file not found: {backup_file}")
            raise FileNotFoundError(f"Backup file not found: {backup_file}")
        
        if not backup_file.is_file():
            logger.error(f"❌ Backup path is not a file: {backup_file}")
            raise ValueError(f"Backup path is not a file: {backup_file}")
        
        try:
            import tarfile
            logger.debug(f"📦 Extracting metadata from backup: {backup_file.name}")
            
            with tarfile.open(backup_file, 'r:gz') as tar_archive:
                # Locate backup metadata file in archive
                metadata_file = self._locate_metadata_file_in_archive(tar_archive)
                if not metadata_file:
                    logger.warning(f"⚠️ No backup_info.json found in {backup_file.name}")
                    return None
                
                # Extract and decode metadata content
                metadata_content = self._decode_backup_metadata_content(tar_archive, metadata_file)
                if not metadata_content:
                    logger.error(f"❌ Failed to decode metadata from {backup_file.name}")
                    return None
                
                # Parse and validate metadata
                backup_metadata = self._parse_and_validate_metadata(metadata_content, backup_file)
                if backup_metadata:
                    logger.info(f"✅ Successfully extracted metadata from {backup_file.name}")
                    return backup_metadata
                else:
                    logger.error(f"❌ Failed to validate metadata from {backup_file.name}")
                    return None
                    
        except (FileNotFoundError, ValueError):
            # Re-raise our custom exceptions
            raise
        except tarfile.TarError as e:
            logger.error(f"❌ Archive error while extracting metadata from {backup_file.name}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error extracting metadata from {backup_file.name}: {e}")
            return None
    
    def _locate_metadata_file_in_archive(self, tar_archive) -> Optional[str]:
        """
        Locate backup_info.json file within the tar archive.
        
        Args:
            tar_archive: Open tarfile archive object
            
        Returns:
            Path to metadata file if found, None otherwise
        """
        try:
            for member in tar_archive.getmembers():
                if member.isfile() and member.name.endswith('backup_info.json'):
                    logger.debug(f"🎯 Found metadata file: {member.name}")
                    return member.name
            
            logger.debug("🔍 No backup_info.json found in archive")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error searching for metadata file in archive: {e}")
            return None
    
    def _decode_backup_metadata_content(self, tar_archive, metadata_file_path: str) -> Optional[str]:
        """
        Extract and decode backup metadata content from archive.
        
        Args:
            tar_archive: Open tarfile archive object
            metadata_file_path: Path to metadata file within archive
            
        Returns:
            Decoded metadata content as string if successful, None otherwise
        """
        try:
            # Extract file content from archive
            metadata_member = tar_archive.getmember(metadata_file_path)
            if metadata_member.isfile():
                file_content_bytes = tar_archive.extractfile(metadata_member).read()
                
                # Validate content is not empty
                if not file_content_bytes:
                    logger.error(f"❌ Metadata file {metadata_file_path} is empty")
                    return None
                
                # Decode with proper error handling
                try:
                    decoded_content = file_content_bytes.decode('utf-8')
                    logger.debug(f"✅ Successfully decoded metadata file ({len(decoded_content)} characters)")
                    return decoded_content
                except UnicodeDecodeError as e:
                    logger.error(f"❌ UTF-8 decoding failed for metadata file {metadata_file_path}: {e}")
                    logger.error(f"   File size: {len(file_content_bytes)} bytes")
                    logger.error(f"   First 100 bytes (hex): {file_content_bytes[:100].hex()}")
                    raise
                    
        except KeyError:
            logger.error(f"❌ Metadata file {metadata_file_path} not found in archive")
            return None
        except Exception as e:
            logger.error(f"❌ Error extracting metadata file {metadata_file_path}: {e}")
            return None
    
    def _parse_and_validate_metadata(self, metadata_content: str, backup_file: Path) -> Optional[Dict]:
        """
        Parse and validate metadata JSON content.
        
        Args:
            metadata_content: Raw JSON metadata content
            backup_file: Original backup file path
            
        Returns:
            Validated backup metadata dictionary if successful, None otherwise
        """
        try:
            # Parse JSON content
            backup_metadata = json.loads(metadata_content)
            
            # Validate required fields
            required_fields = ['backup_type', 'timestamp', 'created_at']
            missing_fields = [field for field in required_fields if field not in backup_metadata]
            
            if missing_fields:
                logger.error(f"❌ Missing required metadata fields: {missing_fields}")
                return None
            
            # Add file system metadata
            backup_metadata.update({
                'path': str(backup_file.with_suffix('')),
                'compressed': True,
                'file_size_bytes': backup_file.stat().st_size,
                'file_modified': datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
            })
            
            # Log successful validation
            logger.debug(f"✅ Metadata validation successful")
            logger.debug(f"   Backup type: {backup_metadata['backup_type']}")
            logger.debug(f"   Created: {backup_metadata['created_at']}")
            logger.debug(f"   Databases: {backup_metadata.get('databases_backed_up', [])}")
            
            return backup_metadata
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in metadata file: {e}")
            logger.error(f"   JSON error position: Line {e.lineno}, Column {e.colno}")
            logger.error(f"   Content preview: {metadata_content[:200]}...")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error parsing metadata: {e}")
            return None
    
    # ========================================================================
    # RECOVERY SYSTEM
    # ========================================================================
    
    def recover_from_corruption(self, validation_results: Dict) -> bool:
        """
        Attempt to recover from database corruption
        
        Args:
            validation_results: Results from validate_all_databases()
            
        Returns:
            True if recovery successful, False otherwise
        """
        logger.warning("🛠️ Starting database corruption recovery...")
        
        try:
            # Determine recovery strategy based on validation results
            sqlite_valid = validation_results['sqlite_validation'].get('valid', False)
            chroma_valid = validation_results['chroma_validation'].get('valid', False)
            
            # Strategy 1: SQLite corrupted, ChromaDB okay
            if not sqlite_valid and chroma_valid:
                logger.info("🔧 SQLite corruption detected, attempting recovery...")
                return self._recover_sqlite_database()
            
            # Strategy 2: ChromaDB corrupted, SQLite okay  
            elif sqlite_valid and not chroma_valid:
                logger.info("🔧 ChromaDB corruption detected, attempting recovery...")
                return self._recover_chroma_database()
            
            # Strategy 3: Both corrupted
            elif not sqlite_valid and not chroma_valid:
                logger.warning("⚠️ Both databases corrupted, attempting full recovery...")
                return self._recover_full_database()
            
            else:
                logger.info("✅ No corruption detected, no recovery needed")
                return True
                
        except Exception as e:
            logger.error(f"❌ Database recovery failed: {e}")
            return False
    
    def _recover_sqlite_database(self) -> bool:
        """Attempt to recover corrupted SQLite database"""
        try:
            # Create backup before recovery attempt
            backup_path = self.create_backup("pre_recovery", force=True)
            if not backup_path:
                logger.error("❌ Could not create pre-recovery backup")
                return False
            
            # Try SQLite repair
            conn = sqlite3.connect(str(self.sqlite_db))
            try:
                cursor = conn.cursor()
                
                # Attempt integrity repair
                cursor.execute("PRAGMA integrity_check;")
                integrity_result = cursor.fetchone()[0]
                
                if integrity_result != "ok":
                    logger.warning(f"🔧 SQLite integrity check failed: {integrity_result}")
                    
                    # Try to export/import to repair
                    logger.info("🔧 Attempting SQLite export/import repair...")
                    
                    # Get all data
                    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';")
                    tables_info = cursor.fetchall()
                    
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                    table_names = [row[0] for row in cursor.fetchall()]
                    
                    # Export data
                    backup_data = {}
                    for table_name in table_names:
                        cursor.execute(f"SELECT * FROM {table_name}")
                        backup_data[table_name] = cursor.fetchall()
                    
                    # Get schema
                    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                    schemas = cursor.fetchall()
                    
                    # Recreate database
                    conn.close()
                    
                    # Remove corrupted database
                    self.sqlite_db.unlink()
                    
                    # Recreate
                    conn = sqlite3.connect(str(self.sqlite_db))
                    cursor = conn.cursor()
                    
                    # Recreate tables
                    for schema_info in schemas:
                        if schema_info[0]:
                            cursor.execute(schema_info[0])
                    
                    # Restore data
                    for table_name, rows in backup_data.items():
                        if rows:
                            placeholders = ', '.join(['?' for _ in rows[0]])
                            cursor.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)
                    
                    conn.commit()
                    logger.info("✅ SQLite database successfully repaired")
                    
            finally:
                conn.close()
            
            # Verify repair
            validation_results = self._validate_sqlite_database()
            if validation_results['valid']:
                logger.info("✅ SQLite database recovery successful")
                return True
            else:
                logger.error(f"❌ SQLite database repair failed: {validation_results['error']}")
                return False
                
        except Exception as e:
            logger.error(f"❌ SQLite recovery error: {e}")
            return False
    
    def _recover_chroma_database(self) -> bool:
        """Attempt to recover corrupted ChromaDB"""
        try:
            # Strategy: Remove corrupted binary files and let ChromaDB regenerate them
            logger.info("🧹 Cleaning corrupted ChromaDB binary files...")
            
            # Remove corrupted ChromaDB directory
            if self.chroma_dir.exists():
                backup_path = self.create_backup("pre_recovery", force=True)
                if not backup_path:
                    logger.error("❌ Could not create pre-recovery backup")
                    return False
                
                shutil.rmtree(self.chroma_dir)
                logger.info("🗑️ Removed corrupted ChromaDB directory")
            
            # Let ChromaDB recreate on next startup
            logger.info("🔄 ChromaDB will be recreated on next startup")
            return True
            
        except Exception as e:
            logger.error(f"❌ ChromaDB recovery error: {e}")
            return False
    
    def _recover_full_database(self) -> bool:
        """Attempt to recover both databases"""
        logger.info("🔧 Attempting full database recovery...")
        
        # Restore from latest backup
        backups = self.list_backups()
        if not backups:
            logger.error("❌ No backups available for recovery")
            return False
        
        # Try latest backup first
        latest_backup = backups[0]
        logger.info(f"📦 Restoring from backup: {latest_backup['created_at']}")
        
        try:
            if latest_backup.get('compressed', True):
                self._restore_compressed_backup(latest_backup['path'])
            else:
                self._restore_directory_backup(latest_backup['path'])
            
            # Verify restoration
            validation_results = self.validate_all_databases()
            if validation_results['overall_status'] in ['valid', 'recoverable']:
                logger.info("✅ Full database recovery successful")
                return True
            else:
                logger.error("❌ Database restoration failed validation")
                return False
                
        except Exception as e:
            logger.error(f"❌ Full recovery error: {e}")
            return False
    
    def _restore_compressed_backup(self, backup_path: str):
        """Restore from compressed backup"""
        try:
            import tarfile
            
            backup_file = Path(backup_path)
            if not backup_file.exists():
                backup_file = Path(backup_path + '.tar.gz')
            
            with tarfile.open(backup_file, 'r:gz') as tar:
                tar.extractall(self.data_dir.parent)
            
            logger.info("✅ Restored from compressed backup")
            
        except Exception as e:
            logger.error(f"❌ Compressed backup restore failed: {e}")
            raise
    
    def _restore_directory_backup(self, backup_path: str):
        """Restore from directory backup"""
        try:
            backup_dir = Path(backup_path)
            if backup_dir.exists():
                # Remove existing data directory first to avoid conflicts
                if self.data_dir.exists():
                    shutil.rmtree(self.data_dir)
                
                # Copy backup to data directory
                for item in backup_dir.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, self.data_dir / item.name)
                    else:
                        shutil.copy2(item, self.data_dir / item.name)
                
                logger.info("✅ Restored from directory backup")
            
        except Exception as e:
            logger.error(f"❌ Directory backup restore failed: {e}")
            raise
    
    # ========================================================================
    # GRACEFUL SHUTDOWN
    # ========================================================================
    
    def setup_graceful_shutdown(self):
        """Set up graceful shutdown handlers"""
        import signal
        import atexit
        
        def shutdown_handler(signum, frame):
            logger.info("🛑 Graceful shutdown initiated...")
            self.graceful_shutdown()
            exit(0)
        
        def cleanup_on_exit():
            logger.info("🧹 Performing cleanup on exit...")
            self.graceful_shutdown()
        
        # Register signal handlers
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
        
        # Register atexit cleanup
        atexit.register(cleanup_on_exit)
        
        logger.info("🛡️ Graceful shutdown handlers registered")
    
    def graceful_shutdown(self):
        """Perform graceful shutdown with database protection"""
        try:
            logger.info("💾 Creating shutdown backup...")
            backup_path = self.create_backup("pre_shutdown", force=True)
            
            if backup_path:
                logger.info(f"✅ Shutdown backup created: {backup_path}")
            
            # Additional cleanup can be added here
            logger.info("🛡️ Database protection shutdown complete")
            
        except Exception as e:
            logger.error(f"❌ Graceful shutdown error: {e}")
    
    # ========================================================================
    # HEALTH MONITORING
    # ========================================================================
    
    def get_health_status(self) -> Dict:
        """Get current health status of database protection system"""
        return {
            'timestamp': datetime.now().isoformat(),
            'last_backup_time': self.last_backup_time,
            'backup_count': self.backup_count,
            'validation_failures': len(self.validation_failures),
            'data_directory_exists': self.data_dir.exists(),
            'backup_directory_exists': self.backup_dir.exists(),
            'databases_exist': {
                'sqlite': self.sqlite_db.exists(),
                'chroma': self.chroma_dir.exists()
            }
        }

# Global instance
_database_protector = None

def get_database_protector() -> DatabaseProtector:
    """Get global database protector instance"""
    global _database_protector
    if _database_protector is None:
        _database_protector = DatabaseProtector()
    return _database_protector