import json
import shutil
import tarfile
import time
from datetime import datetime
from pathlib import Path

from serin.d1_3_state_core.db_protect.core import (
    DatabaseProtectorCore,
    DatabaseRecoveryError,
)
from serin.d1_3_state_core.logger import logger


class DatabaseProtectorBackup(DatabaseProtectorCore):
    def list_backups(self) -> list[dict]:
        backups = []
        try:
            for backup_file in self.backup_dir.glob("*.tar.gz"):
                try:
                    backup_info = self._extract_and_validate_backup_metadata(backup_file)
                    if backup_info:
                        backups.append(backup_info)
                except Exception as e:
                    logger.warning(f" Could not read backup info: {e}")
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
            backups.sort(key=lambda x: x['created_at'], reverse=True)
        except Exception as e:
            logger.error(f" Error listing backups: {e}")
        return backups

    def create_backup(self, backup_type: str = "manual", force: bool = False) -> str:
        try:
            current_time = time.time()
            if backup_type == "automatic" and not force:
                if current_time - self.last_backup_time < self.backup_interval:
                    logger.debug(f"Skipping automatic backup (last: {current_time - self.last_backup_time}s ago)")
                    return ""
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{backup_type}_{timestamp}"
            backup_path = self.backup_dir / backup_name
            logger.info(f" Creating {backup_type} backup: {backup_name}")
            backup_path.mkdir(parents=True, exist_ok=True)
            backup_info = {
                'backup_type': backup_type,
                'timestamp': timestamp,
                'created_at': datetime.now().isoformat(),
                'bot_version': 'unknown',
                'databases_backed_up': [],
                'errors': []
            }
            if self.sqlite_db.exists():
                try:
                    backup_sqlite = backup_path / "bot_data.db"
                    shutil.copy2(self.sqlite_db, backup_sqlite)
                    backup_info['databases_backed_up'].append('SQLite')
                    logger.debug(" SQLite database backed up")
                except Exception as e:
                    backup_info['errors'].append(f"SQLite backup error: {e}")
                    logger.error(f" SQLite backup failed: {e}")
            if self.chroma_dir.exists():
                try:
                    backup_chroma = backup_path / "chroma_data"
                    shutil.copytree(self.chroma_dir, backup_chroma)
                    backup_info['databases_backed_up'].append('ChromaDB')
                    logger.debug(" ChromaDB directory backed up")
                except Exception as e:
                    backup_info['errors'].append(f"ChromaDB backup error: {e}")
                    logger.error(f" ChromaDB backup failed: {e}")
            metadata_file = backup_path / "backup_info.json"
            with open(metadata_file, 'w') as f:
                json.dump(backup_info, f, indent=2)
            if backup_info['databases_backed_up']:
                self._compress_backup(backup_path)
                self.backup_count += 1
                self.last_backup_time = current_time
                self._cleanup_old_backups()
                logger.info(f" {backup_type} backup completed: {backup_name}")
                return str(backup_path)
            else:
                shutil.rmtree(backup_path)
                logger.warning(f" {backup_type} backup failed - no databases backed up")
                return ""
        except Exception as e:
            logger.error(f" Backup creation failed: {e}")
            raise DatabaseRecoveryError(f"Backup creation failed: {e}")

    def _compress_backup(self, backup_path: Path) -> None:
        try:
            shutil.make_archive(
                str(backup_path.with_suffix('')),
                'gztar',
                root_dir=str(backup_path.parent),
                base_dir=backup_path.name
            )
            shutil.rmtree(backup_path)
            logger.debug(" Backup compressed successfully")
        except Exception as e:
            logger.warning(f" Backup compression failed: {e}")
            logger.info(f" Backup completed without compression: {backup_path.name}")

    def _cleanup_old_backups(self) -> None:
        try:
            backup_files = list(self.backup_dir.glob("*.tar.gz"))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for backup_file in backup_files[self.max_backups:]:
                backup_file.unlink()
                logger.debug(f" Removed old backup: {backup_file.name}")
            for backup_dir in self.backup_dir.iterdir():
                if backup_dir.is_dir():
                    backup_files.append(backup_dir)
            backup_files = [f for f in backup_files if f.exists()]
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for backup_item in backup_files[self.max_backups:]:
                if backup_item.is_dir():
                    shutil.rmtree(backup_item)
                else:
                    backup_item.unlink()
                logger.debug(f" Removed old backup: {backup_item.name}")
        except Exception as e:
            logger.warning(f" Backup cleanup failed: {e}")

    def _extract_and_validate_backup_metadata(self, backup_file: Path) -> dict | None:
        if not backup_file.exists():
            logger.error(f" Backup file not found: {backup_file}")
            raise FileNotFoundError(f"Backup file not found: {backup_file}")
        if not backup_file.is_file():
            logger.error(f" Backup path is not a file: {backup_file}")
            raise ValueError(f"Backup path is not a file: {backup_file}")
        try:
            logger.debug(f" Extracting metadata from backup: {backup_file.name}")
            with tarfile.open(backup_file, 'r:gz') as tar_archive:
                metadata_file = self._locate_metadata_file_in_archive(tar_archive)
                if not metadata_file:
                    logger.warning(f" No backup_info.json found in {backup_file.name}")
                    return None
                metadata_content = self._decode_backup_metadata_content(tar_archive, metadata_file)
                if not metadata_content:
                    logger.error(f" Failed to decode metadata from {backup_file.name}")
                    return None
                backup_metadata = self._parse_and_validate_metadata(metadata_content, backup_file)
                if backup_metadata:
                    logger.info(f" Successfully extracted metadata from {backup_file.name}")
                    return backup_metadata
                else:
                    logger.error(f" Failed to validate metadata from {backup_file.name}")
                    return None
        except (FileNotFoundError, ValueError):
            raise
        except tarfile.TarError as e:
            logger.error(f" Archive error while extracting metadata from {backup_file.name}: {e}")
            return None
        except Exception as e:
            logger.error(f" Unexpected error extracting metadata from {backup_file.name}: {e}")
            return None

    def _locate_metadata_file_in_archive(self, tar_archive) -> str | None:
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

    def _decode_backup_metadata_content(self, tar_archive, metadata_file_path: str) -> str | None:
        try:
            metadata_member = tar_archive.getmember(metadata_file_path)
            if metadata_member.isfile():
                file_content_bytes = tar_archive.extractfile(metadata_member).read()
                if not file_content_bytes:
                    logger.error(f" Metadata file {metadata_file_path} is empty")
                    return None
                try:
                    decoded_content = file_content_bytes.decode('utf-8')
                    logger.debug(f" Successfully decoded metadata file ({len(decoded_content)} characters)")
                    return decoded_content
                except UnicodeDecodeError as e:
                    logger.error(f" UTF-8 decoding failed for metadata file {metadata_file_path}: {e}")
                    raise
        except KeyError:
            logger.error(f" Metadata file {metadata_file_path} not found in archive")
            return None
        except Exception as e:
            logger.error(f" Error extracting metadata file {metadata_file_path}: {e}")
            return None

    def _parse_and_validate_metadata(self, metadata_content: str, backup_file: Path) -> dict | None:
        try:
            backup_metadata = json.loads(metadata_content)
            required_fields = ['backup_type', 'timestamp', 'created_at']
            missing_fields = [field for field in required_fields if field not in backup_metadata]
            if missing_fields:
                logger.error(f" Missing required metadata fields: {missing_fields}")
                return None
            backup_metadata.update({
                'path': str(backup_file.with_suffix('')),
                'compressed': True,
                'file_size_bytes': backup_file.stat().st_size,
                'file_modified': datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
            })
            logger.debug(" Metadata validation successful")
            logger.debug(f"   Backup type: {backup_metadata['backup_type']}")
            logger.debug(f"   Created: {backup_metadata['created_at']}")
            logger.debug(f"   Databases: {backup_metadata.get('databases_backed_up', [])}")
            return backup_metadata
        except json.JSONDecodeError as e:
            logger.error(f" Invalid JSON in metadata file: {e}")
            return None
        except Exception as e:
            logger.error(f" Unexpected error parsing metadata: {e}")
            return None
