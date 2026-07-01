import sqlite3
import time
from datetime import datetime
from pathlib import Path

from serin.d1_3_state_core.logger import logger


class DatabaseValidationError(Exception):
    pass


class DatabaseRecoveryError(Exception):
    pass


class DatabaseProtectorCore:
    def __init__(self, data_dir: str = "./bot_data", backup_dir: str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.backup_dir = Path(backup_dir) if backup_dir else self.data_dir / "backups"
        if not isinstance(self.backup_dir, Path):
            self.backup_dir = Path(self.backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.max_backups = 50
        self.backup_interval = 3600
        self.validation_enabled = True

        self.chroma_dir = self.data_dir / "chroma_data"
        self.sqlite_db = self.data_dir / "bot_data.db"

        self.last_backup_time = 0
        self.backup_count = 0
        self.validation_failures = []

        logger.info(" Database Protection System initialized")
        logger.info(f"   Data directory: {self.data_dir}")
        logger.info(f"    Backup directory: {self.backup_dir}")
        logger.info(f"    Validation: {'ENABLED' if self.validation_enabled else 'DISABLED'}")

    def validate_all_databases(self) -> dict:
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

            sqlite_results = self._validate_sqlite_database()
            results['sqlite_validation'] = sqlite_results

            if not sqlite_results['valid']:
                results['errors'].append(f"SQLite validation failed: {sqlite_results['error']}")

            chroma_results = self._validate_chroma_database()
            results['chroma_validation'] = chroma_results

            if not chroma_results['valid']:
                results['errors'].append(f"ChromaDB validation failed: {chroma_results['error']}")

            all_missing = all(
                'does not exist' in err or 'missing files' in err or 'Missing required tables' in err
                for err in results['errors']
            )

            if not results['errors']:
                results['overall_status'] = 'valid'
                logger.info(" Database validation PASSED")
            elif all_missing:
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

    def _validate_sqlite_database(self) -> dict:
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

            try:
                with open(self.sqlite_db, 'rb') as f:
                    f.read(1024)
                results['readable'] = True
            except Exception as e:
                results['error'] = f"Cannot read database: {e}"
                return results

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

                cursor.execute("PRAGMA page_count;")
                results['page_count'] = cursor.fetchone()[0]

                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                tables = [row[0] for row in cursor.fetchall()]

                required_tables = ['users', 'relationships', 'recent_messages']
                missing_tables = [t for t in required_tables if t not in tables]

                if missing_tables and len(tables) > 1:
                    results['error'] = f"Missing required tables: {missing_tables}"
                else:
                    results['schema_valid'] = True
                    results['valid'] = True

            finally:
                conn.close()

        except Exception as e:
            results['error'] = f"SQLite validation error: {e}"

        return results

    def _validate_chroma_database(self) -> dict:
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

            sqlite_path = self.chroma_dir / "chroma.sqlite3"
            if sqlite_path.exists():
                results['sqlite_component_valid'] = True
                results['file_sizes']['sqlite'] = sqlite_path.stat().st_size
            else:
                results['missing_files'].append('chroma.sqlite3')

            for subdir in self.chroma_dir.iterdir():
                if subdir.is_dir():
                    required_files = ['header.bin', 'length.bin', 'link_lists.bin', 'data_level0.bin']

                    for req_file in required_files:
                        file_path = subdir / req_file
                        if file_path.exists():
                            results['file_sizes'][f"{subdir.name}/{req_file}"] = file_path.stat().st_size

                            if req_file == 'link_lists.bin' and file_path.stat().st_size == 0:
                                results['binary_files_valid'] = False
                                results['error'] = f"Empty binary file: {req_file}"
                                return results
                        else:
                            results['missing_files'].append(f"{subdir.name}/{req_file}")

            if results['missing_files']:
                if len(results['missing_files']) > 2:
                    results['error'] = f"Too many missing files: {results['missing_files']}"
                else:
                    results['valid'] = True
            else:
                results['binary_files_valid'] = True
                results['valid'] = True

        except Exception as e:
            results['error'] = f"ChromaDB validation error: {e}"

        return results


_database_protector = None  # type: ignore


def get_database_protector() -> "DatabaseProtector":  # noqa: F821
    global _database_protector
    if _database_protector is None:
        from serin.d1_3_state_core.db_protect import DatabaseProtector
        _database_protector = DatabaseProtector()
    return _database_protector
