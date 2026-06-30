"""Backup metadata extraction and validation."""

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
            logger.error(f" Backup file not found: {backup_file}")
            raise FileNotFoundError(f"Backup file not found: {backup_file}")
        
        if not backup_file.is_file():
            logger.error(f" Backup path is not a file: {backup_file}")
            raise ValueError(f"Backup path is not a file: {backup_file}")
        
        try:
            import tarfile
            logger.debug(f" Extracting metadata from backup: {backup_file.name}")
            
            with tarfile.open(backup_file, 'r:gz') as tar_archive:
                # Locate backup metadata file in archive
                metadata_file = self._locate_metadata_file_in_archive(tar_archive)
                if not metadata_file:
                    logger.warning(f" No backup_info.json found in {backup_file.name}")
                    return None
                
                # Extract and decode metadata content
                metadata_content = self._decode_backup_metadata_content(tar_archive, metadata_file)
                if not metadata_content:
                    logger.error(f" Failed to decode metadata from {backup_file.name}")
                    return None
                
                # Parse and validate metadata
                backup_metadata = self._parse_and_validate_metadata(metadata_content, backup_file)
                if backup_metadata:
                    logger.info(f" Successfully extracted metadata from {backup_file.name}")
                    return backup_metadata
                else:
                    logger.error(f" Failed to validate metadata from {backup_file.name}")
                    return None
                    
        except (FileNotFoundError, ValueError):
            # Re-raise our custom exceptions
            raise
        except tarfile.TarError as e:
            logger.error(f" Archive error while extracting metadata from {backup_file.name}: {e}")
            return None
        except Exception as e:
            logger.error(f" Unexpected error extracting metadata from {backup_file.name}: {e}")
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
                    logger.debug(f" Found metadata file: {member.name}")
                    return member.name
            
            logger.debug(" No backup_info.json found in archive")
            return None
            
        except Exception as e:
            logger.error(f" Error searching for metadata file in archive: {e}")
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
                    logger.error(f" Metadata file {metadata_file_path} is empty")
                    return None
                
                # Decode with proper error handling
                try:
                    decoded_content = file_content_bytes.decode('utf-8')
                    logger.debug(f" Successfully decoded metadata file ({len(decoded_content)} characters)")
                    return decoded_content
                except UnicodeDecodeError as e:
                    logger.error(f" UTF-8 decoding failed for metadata file {metadata_file_path}: {e}")
                    logger.error(f"   File size: {len(file_content_bytes)} bytes")
                    logger.error(f"   First 100 bytes (hex): {file_content_bytes[:100].hex()}")
                    raise
                    
        except KeyError:
            logger.error(f" Metadata file {metadata_file_path} not found in archive")
            return None
        except Exception as e:
            logger.error(f" Error extracting metadata file {metadata_file_path}: {e}")
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
                logger.error(f" Missing required metadata fields: {missing_fields}")
                return None
            
            # Add file system metadata
            backup_metadata.update({
                'path': str(backup_file.with_suffix('')),
                'compressed': True,
                'file_size_bytes': backup_file.stat().st_size,
                'file_modified': datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
            })
            
            # Log successful validation
            logger.debug(f" Metadata validation successful")
            logger.debug(f"   Backup type: {backup_metadata['backup_type']}")
            logger.debug(f"   Created: {backup_metadata['created_at']}")
            logger.debug(f"   Databases: {backup_metadata.get('databases_backed_up', [])}")
            
            return backup_metadata
            
        except json.JSONDecodeError as e:
            logger.error(f" Invalid JSON in metadata file: {e}")
            logger.error(f"   JSON error position: Line {e.lineno}, Column {e.colno}")
            logger.error(f"   Content preview: {metadata_content[:200]}...")
            return None
        except Exception as e:
            logger.error(f" Unexpected error parsing metadata: {e}")
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
        logger.warning("🛠 Starting database corruption recovery...")
        
        try:
            # Determine recovery strategy based on validation results
            sqlite_valid = validation_results['sqlite_validation'].get('valid', False)
            chroma_valid = validation_results['chroma_validation'].get('valid', False)
            
            # Strategy 1: SQLite corrupted, ChromaDB okay
            if not sqlite_valid and chroma_valid:
                logger.info(" SQLite corruption detected, attempting recovery...")
                return self._recover_sqlite_database()
            
            # Strategy 2: ChromaDB corrupted, SQLite okay  
            elif sqlite_valid and not chroma_valid:
                logger.info(" ChromaDB corruption detected, attempting recovery...")
                return self._recover_chroma_database()
            
            # Strategy 3: Both corrupted
            elif not sqlite_valid and not chroma_valid:
                logger.warning(" Both databases corrupted, attempting full recovery...")
                return self._recover_full_database()
            
            else:
                logger.info(" No corruption detected, no recovery needed")
                return True
                
        except Exception as e:
            logger.error(f" Database recovery failed: {e}")
            return False
    
    def _recover_sqlite_database(self) -> bool:
        """Attempt to recover corrupted SQLite database"""
        try:
            # Create backup before recovery attempt
            backup_path = self.create_backup("pre_recovery", force=True)
            if not backup_path:
                logger.error(" Could not create pre-recovery backup")
                return False
            
            # Try SQLite repair
            conn = sqlite3.connect(str(self.sqlite_db))
            try:
                cursor = conn.cursor()
                
                # Attempt integrity repair
                cursor.execute("PRAGMA integrity_check;")
                integrity_result = cursor.fetchone()[0]
                
                if integrity_result != "ok":
                    logger.warning(f" SQLite integrity check failed: {integrity_result}")
                    
                    # Try to export/import to repair
                    logger.info(" Attempting SQLite export/import repair...")
                    
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
                    logger.info(" SQLite database successfully repaired")
                    
            finally:
                conn.close()
            
            # Verify repair
            validation_results = self._validate_sqlite_database()
            if validation_results['valid']:
                logger.info(" SQLite database recovery successful")
                return True
            else:
                logger.error(f" SQLite database repair failed: {validation_results['error']}")
                return False
                
        except Exception as e:
            logger.error(f" SQLite recovery error: {e}")
            return False
    
    def _recover_chroma_database(self) -> bool:
        """Attempt to recover corrupted ChromaDB"""
        try:
            # Strategy: Remove corrupted binary files and let ChromaDB regenerate them
            logger.info(" Cleaning corrupted ChromaDB binary files...")
            
            # Remove corrupted ChromaDB directory
            if self.chroma_dir.exists():
                backup_path = self.create_backup("pre_recovery", force=True)
                if not backup_path:
                    logger.error(" Could not create pre-recovery backup")
                    return False
                
                shutil.rmtree(self.chroma_dir)
                logger.info(" Removed corrupted ChromaDB directory")
            
            # Let ChromaDB recreate on next startup
            logger.info(" ChromaDB will be recreated on next startup")
            return True
            
        except Exception as e:
            logger.error(f" ChromaDB recovery error: {e}")
            return False
    
    def _recover_full_database(self) -> bool:
        """Attempt to recover both databases"""
        logger.info(" Attempting full database recovery...")
        
        # Restore from latest backup
        backups = self.list_backups()
        if not backups:
            logger.error(" No backups available for recovery")
            return False
        
        # Try latest backup first
        latest_backup = backups[0]
        logger.info(f" Restoring from backup: {latest_backup['created_at']}")
        
        try:
            if latest_backup.get('compressed', True):
                self._restore_compressed_backup(latest_backup['path'])
            else:
                self._restore_directory_backup(latest_backup['path'])
            
            # Verify restoration
            validation_results = self.validate_all_databases()
            if validation_results['overall_status'] in ['valid', 'recoverable']:
                logger.info(" Full database recovery successful")
                return True
            else:
                logger.error(" Database restoration failed validation")
                return False
                
        except Exception as e:
            logger.error(f" Full recovery error: {e}")
            return False
    
    def _restore_compressed_backup(self, backup_path: str) -> None:
        """Restore from compressed backup"""
        try:
            import tarfile
            
            backup_file = Path(backup_path)
            if not backup_file.exists():
                backup_file = Path(backup_path + '.tar.gz')
            
            with tarfile.open(backup_file, 'r:gz') as tar:
                tar.extractall(self.data_dir.parent)
            
            logger.info(" Restored from compressed backup")
            
        except Exception as e:
            logger.error(f" Compressed backup restore failed: {e}")
            raise
    
    def _restore_directory_backup(self, backup_path: str) -> None:
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
                
                logger.info(" Restored from directory backup")
            
        except Exception as e:
            logger.error(f" Directory backup restore failed: {e}")
            raise
    
    # ========================================================================
    # GRACEFUL SHUTDOWN
    # ========================================================================
    
    def setup_graceful_shutdown(self) -> None:
        """Set up graceful shutdown handlers"""
        import signal
        import atexit
        import os
        
        self._shutdown_in_progress = False
        
        def shutdown_handler(signum, frame):
            # Prevent re-entry
            if self._shutdown_in_progress:
                # Force exit on second Ctrl+C
                logger.info(" Force exit requested")
                os._exit(1)
                return
            
            self._shutdown_in_progress = True
            logger.info(" Graceful shutdown initiated...")
            self.graceful_shutdown()
            # Use os._exit to terminate immediately without triggering more handlers
            os._exit(0)
        
        def cleanup_on_exit():
            if not self._shutdown_in_progress:
                logger.info(" Performing cleanup on exit...")
                self.graceful_shutdown()
        
        # Register signal handlers
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
        
        # Register atexit cleanup
        atexit.register(cleanup_on_exit)
        
        logger.info(" Graceful shutdown handlers registered")
    
    def graceful_shutdown(self) -> None:
        """Perform graceful shutdown with database protection"""
        try:
            logger.info(" Creating shutdown backup...")
            backup_path = self.create_backup("pre_shutdown", force=True)
            
            if backup_path:
                logger.info(f" Shutdown backup created: {backup_path}")
            
            # Additional cleanup can be added here
            logger.info(" Database protection shutdown complete")
            
        except Exception as e:
            logger.error(f" Graceful shutdown error: {e}")
    
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