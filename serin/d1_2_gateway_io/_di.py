"""Dependency injection container for gateway layer."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logging import Logger

_logger: Logger | None = None


def init_gateway(logger: Logger) -> None:
    global _logger
    _logger = logger


def get_logger() -> Logger:
    if _logger is None:
        raise RuntimeError("Gateway not initialized")
    return _logger
