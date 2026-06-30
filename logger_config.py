"""
DEPRECATED: This module has moved to serin.core.logger.
This shim exists for backwards compatibility only. Update your imports.
"""
from serin.core.logger import *  # noqa: F401, F403
from serin.core.logger import logger  # explicit re-export
import warnings
warnings.warn(
    "logger_config is deprecated. Use serin.core.logger instead.",
    DeprecationWarning, stacklevel=2
)
