"""
Centralized logging configuration for Serin Bot.

Features:
- Configurable log level via LOG_LEVEL env var
- Structured JSON option via LOG_FORMAT=json env var
- Rotating file handler (5MB, 5 backups)
- Relative paths resolved from project root
- Correlation IDs for request tracing
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Resolve paths relative to THIS file, not the working directory
_PROJECT_ROOT = Path(__file__).parent
_LOG_DIR = _PROJECT_ROOT / "logs"
_LOG_DIR.mkdir(exist_ok=True)


class ContextFilter(logging.Filter):
    """Inject correlation_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        # LogRecord supports arbitrary attributes via __dict__
        if not hasattr(record, "correlation_id"):
            record.correlation_id = ""  # type: ignore[attr-defined]
        return True


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        correlation_id = getattr(record, "correlation_id", "")
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "file": record.filename,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if correlation_id:
            log_entry["correlation_id"] = correlation_id
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable log formatter for development."""

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )


def setup_logging() -> logging.Logger:
    """Initialize the root logger with console + file handlers."""
    root_logger = logging.getLogger("serin")

    # Guard: if handlers already exist, don't add more
    if root_logger.handlers:
        return root_logger

    # --- Log level from env ---
    log_level_str = os.getenv("LOG_LEVEL", "DEBUG").upper()
    log_level = getattr(logging, log_level_str, logging.DEBUG)

    # --- Formatter selection ---
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    if log_format == "json":
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    root_logger.setLevel(log_level)

    # --- Console handler ---
    console_output = (
        sys.stdout.buffer
        if hasattr(sys.stdout, "buffer")
        else sys.stdout
    )
    try:
        import io
        console_stream = io.TextIOWrapper(console_output, encoding="utf-8")  # type: ignore[arg-type]
    except (AttributeError, TypeError):
        console_stream = sys.stdout  # type: ignore[assignment]

    console_handler = logging.StreamHandler(console_stream)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # --- File handler (rotating, 5MB, 5 backups) ---
    log_file = _LOG_DIR / "serin_ai.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # --- Context filter ---
    context_filter = ContextFilter()
    root_logger.addFilter(context_filter)

    # --- Silence noisy third-party loggers ---
    for noisy_logger_name in (
        "discord",
        "discord.http",
        "discord.gateway",
        "llama_cpp",
        "asyncio",
        "urllib3",
        "PIL",
        "matplotlib",
        "huggingface_hub",
        "sentence_transformers",
        "torch",
        "httpx",
        "httpcore",
    ):
        logging.getLogger(noisy_logger_name).setLevel(logging.WARNING)

    return root_logger


def get_correlation_id() -> str:
    """Generate a short correlation ID for request tracing."""
    return uuid.uuid4().hex[:8]


# Initialize logging when this module is imported
logger = setup_logging()
