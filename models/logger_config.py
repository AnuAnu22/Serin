
import logging
import os
import sys
import io
from logging.handlers import RotatingFileHandler

def setup_logging():
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_file_path = os.path.join(log_directory, "serin_ai.log")

    # Create logger
    logger = logging.getLogger("serin_ai")
    logger.setLevel(logging.DEBUG)  # Set the lowest level to capture all messages

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Console handler - force UTF-8 encoding
    # Use io.TextIOWrapper for compatibility across Python versions
    console_output_stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    console_handler = logging.StreamHandler(console_output_stream)
    console_handler.setLevel(logging.INFO)  # Console shows INFO and above
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (rotates logs after 5MB, keeps 5 backup files)
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)  # File logs all DEBUG messages and above
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Prevent duplicate logs if setup_logging is called multiple times
    # This check should be done before adding handlers, not after.
    # The current logic for `if not logger.handlers:` is flawed as handlers are added before the check.
    # A better approach is to ensure `setup_logging` is called only once, or clear handlers if re-called.
    # For simplicity, assuming it's called once at import.

    # Silence noisy loggers from external libraries
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('llama_cpp').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING) # Pillow library, sometimes noisy
    logging.getLogger('matplotlib').setLevel(logging.WARNING) # If used for plotting
    logging.getLogger('huggingface_hub').setLevel(logging.WARNING) # If used for models

    return logger

# Initialize logging when this module is imported
logger = setup_logging()
