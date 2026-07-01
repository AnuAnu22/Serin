import shutil
import sqlite3
import tarfile
from pathlib import Path

from serin.logger import logger
from serin.state.db_protect.backup import DatabaseProtectorBackup

_SQL_SELECT_ALL = "SELECT * FROM {t}"
_SQL_INSERT_VALUES = "INSERT INTO {t} VALUES ({p})"


def _select_table(table_name: str) -> str:
    return _SQL_SELECT_ALL.format(t=table_name)


def _insert_table(table_name: str, placeholders: str) -> str:
    return _SQL_INSERT_VALUES.format(t=table_name, p=placeholders)


class DatabaseProtectorRecovery(DatabaseProtectorBackup):
    def recover_from_corruption(self, validation_results: dict) -> bool:
        logger.warning("Starting database corruption recovery...")
        try:
            sqlite_valid = validation_results['sqlite_validation'].get('valid', False)
            chroma_valid = validation_results['chroma_validation'].get('valid', False)
            if not sqlite_valid and chroma_valid:
                logger.info(" SQLite corruption detected, attempting recovery...")
                return self._recover_sqlite_database()
            elif sqlite_valid and not chroma_valid:
                logger.info(" ChromaDB corruption detected, attempting recovery...")
                return self._recover_chroma_database()
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
        try:
            backup_path = self.create_backup("pre_recovery", force=True)
            if not backup_path:
                logger.error(" Could not create pre-recovery backup")
                return False
            conn = sqlite3.connect(str(self.sqlite_db))
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                integrity_result = cursor.fetchone()[0]
                if integrity_result != "ok":
                    logger.warning(f" SQLite integrity check failed: {integrity_result}")
                    logger.info(" Attempting SQLite export/import repair...")
                    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';")
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                    table_names = [row[0] for row in cursor.fetchall()]
                    backup_data = {}
                    for table_name in table_names:
                        if not table_name.replace('_', '').isalnum():
                            logger.warning(f" Skipping suspicious table name: {table_name}")
                            continue
                        cursor.execute(_select_table(table_name))
                        backup_data[table_name] = cursor.fetchall()
                    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                    schemas = cursor.fetchall()
                    conn.close()
                    self.sqlite_db.unlink()
                    conn = sqlite3.connect(str(self.sqlite_db))
                    cursor = conn.cursor()
                    for schema_info in schemas:
                        if schema_info[0]:
                            cursor.execute(schema_info[0])
                    for table_name, rows in backup_data.items():
                        if rows:
                            placeholders = ', '.join(['?' for _ in rows[0]])
                            if not table_name.replace('_', '').isalnum():
                                logger.warning(f" Skipping insert into suspicious table: {table_name}")
                                continue
                            cursor.executemany(_insert_table(table_name, placeholders), rows)
                    conn.commit()
                    logger.info(" SQLite database successfully repaired")
            finally:
                conn.close()
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
        try:
            logger.info(" Cleaning corrupted ChromaDB binary files...")
            if self.chroma_dir.exists():
                backup_path = self.create_backup("pre_recovery", force=True)
                if not backup_path:
                    logger.error(" Could not create pre-recovery backup")
                    return False
                shutil.rmtree(self.chroma_dir)
                logger.info(" Removed corrupted ChromaDB directory")
            logger.info(" ChromaDB will be recreated on next startup")
            return True
        except Exception as e:
            logger.error(f" ChromaDB recovery error: {e}")
            return False

    def _recover_full_database(self) -> bool:
        logger.info(" Attempting full database recovery...")
        backups = self.list_backups()
        if not backups:
            logger.error(" No backups available for recovery")
            return False
        latest_backup = backups[0]
        logger.info(f" Restoring from backup: {latest_backup['created_at']}")
        try:
            if latest_backup.get('compressed', True):
                self._restore_compressed_backup(latest_backup['path'])
            else:
                self._restore_directory_backup(latest_backup['path'])
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
        try:
            backup_file = Path(backup_path)
            if not backup_file.exists():
                backup_file = Path(backup_path + '.tar.gz')
            with tarfile.open(backup_file, 'r:gz') as tar:
                safe_members = [m for m in tar.getmembers() if not m.name.startswith('/') and '..' not in m.name]
                tar.extractall(self.data_dir.parent, members=safe_members, filter='data')
            logger.info(" Restored from compressed backup")
        except Exception as e:
            logger.error(f" Compressed backup restore failed: {e}")
            raise

    def _restore_directory_backup(self, backup_path: str) -> None:
        try:
            backup_dir = Path(backup_path)
            if backup_dir.exists():
                if self.data_dir.exists():
                    shutil.rmtree(self.data_dir)
                for item in backup_dir.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, self.data_dir / item.name)
                    else:
                        shutil.copy2(item, self.data_dir / item.name)
                logger.info(" Restored from directory backup")
        except Exception as e:
            logger.error(f" Directory backup restore failed: {e}")
            raise
