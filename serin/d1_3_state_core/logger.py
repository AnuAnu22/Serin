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
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import IO, Any, Protocol, cast, runtime_checkable

# Resolve paths relative to THIS file, not the working directory
_PROJECT_ROOT = Path(__file__).parent
_LOG_DIR = _PROJECT_ROOT / "logs"
_LOG_DIR.mkdir(exist_ok=True)

# Custom SUCCESS level (between INFO and WARNING)
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

def success(self: logging.Logger, message: str, *args: object, **kwargs: Any) -> None:
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kwargs)

setattr(logging.Logger, 'success', success)


@runtime_checkable
class LoggerProtocol(Protocol):
    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def info(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def error(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def success(self, msg: str, *args: Any, **kwargs: Any) -> None: ...


class ContextFilter(logging.Filter):
    """Inject correlation_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        # LogRecord supports arbitrary attributes via __dict__
        if not hasattr(record, "correlation_id"):
            record.correlation_id = ""  # type: ignore[attr-defined]
        return True


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for production log aggregation.
    Captures extra= dict fields passed by the caller.
    """

    def format(self, record: logging.LogRecord) -> str:
        correlation_id = getattr(record, "correlation_id", "")
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
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

        # Include any extra= fields passed by the caller
        for key, val in record.__dict__.items():
            if key not in ("args", "asctime", "created", "exc_info", "exc_text",
                           "filename", "funcName", "levelname", "levelno", "lineno",
                           "module", "msecs", "message", "msg", "name", "pathname",
                           "process", "processName", "relativeCreated", "stack_info",
                           "thread", "threadName", "correlation_id"):
                log_entry[key] = str(val) if not isinstance(val, (str, int, float, bool, list, dict, type(None))) else val

        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable log formatter for development (no color)."""

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )


class ColoredFormatter(TextFormatter):
    """Same as TextFormatter but with ANSI color codes for the console."""

    _LEVEL_COLORS = {
        'CRITICAL': '\033[1;31m',
        'ERROR': '\033[31m',
        'WARNING': '\033[33m',
        'SUCCESS': '\033[32m',
        'INFO': '\033[0m',
        'DEBUG': '\033[90m',
    }
    _RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        color = self._LEVEL_COLORS.get(record.levelname, self._RESET)
        formatted = super().format(record)
        if record.levelno >= logging.WARNING:
            return f"{color}{formatted}{self._RESET}"
        if record.levelname == 'SUCCESS':
            return f"{color}{formatted}{self._RESET}"
        return formatted


def setup_logging() -> LoggerProtocol:
    """Initialize the root logger with console + file handlers."""
    root_logger = logging.getLogger("serin")

    # Guard: if handlers already exist, don't add more
    if root_logger.handlers:
        return cast(LoggerProtocol, root_logger)

    # --- Log level from env ---
    log_level_str = os.getenv("LOG_LEVEL", "DEBUG").upper()
    log_level = getattr(logging, log_level_str, logging.DEBUG)

    # --- Formatter selection ---
    log_format = os.getenv("LOG_FORMAT", "text").lower()

    root_logger.setLevel(log_level)

    # --- Console handler (colored for text, plain for json) ---
    try:
        import io
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            console_stream: IO[str] = io.TextIOWrapper(buf, encoding="utf-8")
        else:
            console_stream = sys.stdout
    except (AttributeError, TypeError):
        console_stream = sys.stdout

    console_handler = logging.StreamHandler(console_stream)
    if log_format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(ColoredFormatter())
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # --- File handler (rotating, 5MB, 5 backups, no color) ---
    log_file = _LOG_DIR / "serin_ai.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    if log_format == "json":
        file_handler.setFormatter(JSONFormatter())
    else:
        file_handler.setFormatter(TextFormatter())
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

    return cast(LoggerProtocol, root_logger)


logger = setup_logging()


def get_correlation_id() -> str:
    """Generate a short correlation ID for request tracing."""
    return uuid.uuid4().hex[:8]


# Initialize logging when this module is imported
logger = setup_logging()
