import os
from datetime import datetime

from serin.d1_3_state_core.db_protect.recovery import DatabaseProtectorRecovery
from serin.d1_3_state_core.logger import logger


class DatabaseProtectorShutdown(DatabaseProtectorRecovery):
    def setup_graceful_shutdown(self) -> None:
        import atexit
        import signal
        self._shutdown_in_progress = False
        def shutdown_handler(signum, frame):
            if self._shutdown_in_progress:
                logger.info(" Force exit requested")
                os._exit(1)
                return
            self._shutdown_in_progress = True
            logger.info(" Graceful shutdown initiated...")
            self.graceful_shutdown()
            os._exit(0)
        def cleanup_on_exit():
            if not self._shutdown_in_progress:
                logger.info(" Performing cleanup on exit...")
                self.graceful_shutdown()
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
        atexit.register(cleanup_on_exit)
        logger.info(" Graceful shutdown handlers registered")

    def graceful_shutdown(self) -> None:
        try:
            logger.info(" Creating shutdown backup...")
            backup_path = self.create_backup("pre_shutdown", force=True)
            if backup_path:
                logger.info(f" Shutdown backup created: {backup_path}")
            logger.info(" Database protection shutdown complete")
        except Exception as e:
            logger.error(f" Graceful shutdown error: {e}")

    def get_health_status(self) -> dict:
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
