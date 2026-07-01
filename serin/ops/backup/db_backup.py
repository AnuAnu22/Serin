"""Database backup creation, compression, and metadata management."""
import os
import json
import gzip
import tarfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from serin.state.logger import logger


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
            
            logger.info(f" Creating {backup_type} backup: {backup_name}")
            
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
                    logger.debug(" SQLite database backed up")
                except Exception as e:
                    backup_info['errors'].append(f"SQLite backup error: {e}")
                    logger.error(f" SQLite backup failed: {e}")
            
            # Backup ChromaDB directory
            if self.chroma_dir.exists():
                try:
                    backup_chroma = backup_path / "chroma_data"
                    shutil.copytree(self.chroma_dir, backup_chroma)
                    backup_info['databases_backed_up'].append('ChromaDB')
                    logger.debug(" ChromaDB directory backed up")
                except Exception as e:
                    backup_info['errors'].append(f"ChromaDB backup error: {e}")
                    logger.error(f" ChromaDB backup failed: {e}")
            
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
                
                logger.info(f" {backup_type} backup completed: {backup_name}")
                return str(backup_path)
            else:
                # Remove empty backup directory
                shutil.rmtree(backup_path)
                logger.warning(f" {backup_type} backup failed - no databases backed up")
                return ""
                
        except Exception as e:
            logger.error(f" Backup creation failed: {e}")
            raise DatabaseRecoveryError(f"Backup creation failed: {e}")
    
    def _compress_backup(self, backup_path: Path) -> None:
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
            
            logger.debug(f" Backup compressed successfully")
            
        except Exception as e:
            logger.warning(f" Backup compression failed: {e}")
            # Don't fail the backup process if compression fails
            logger.info(f" Backup completed without compression: {backup_path.name}")
    
    def _cleanup_old_backups(self) -> None:
        """Remove old backups beyond retention limit"""
        try:
            backup_files = list(self.backup_dir.glob("*.tar.gz"))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove excess backups
            for backup_file in backup_files[self.max_backups:]:
                backup_file.unlink()
                logger.debug(f" Removed old backup: {backup_file.name}")
            
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
                logger.debug(f" Removed old backup: {backup_item.name}")
                
        except Exception as e:
            logger.warning(f" Backup cleanup failed: {e}")
    
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
                    logger.warning(f" Could not read backup info: {e}")
            
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
                            logger.warning(f" Could not read backup metadata: {e}")
            
            # Sort by creation time
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            
        except Exception as e:
            logger.error(f" Error listing backups: {e}")
        
        return backups
    