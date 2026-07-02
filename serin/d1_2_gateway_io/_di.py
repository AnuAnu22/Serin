"""Dependency injection container for gateway layer."""
from serin.d1_3_state_core.logger import LoggerProtocol

_logger: LoggerProtocol | None = None


def init_gateway(logger: LoggerProtocol) -> None:
    global _logger
    _logger = logger


def get_logger() -> LoggerProtocol:
    if _logger is None:
        raise RuntimeError("Gateway not initialized")
    return _logger
