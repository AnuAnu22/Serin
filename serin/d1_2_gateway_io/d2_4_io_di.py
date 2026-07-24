"""Dependency injection container for gateway layer."""
from serin.d1_4_config_base.d2_3_logger import LoggerProtocol

_logger: LoggerProtocol | None = None


def init_gateway(logger: LoggerProtocol) -> None:
    global _logger
    _logger = logger


def get_logger() -> LoggerProtocol:
    if _logger is None:
        raise RuntimeError("Gateway not initialized")
    return _logger
