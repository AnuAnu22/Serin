"""
DEPRECATED: This module has moved to serin.core.config.
This shim exists for backwards compatibility only. Update your imports.
"""
from serin.core.config import *  # noqa: F401, F403
from serin.core.config import config, BotConfig  # explicit re-exports
import warnings
warnings.warn(
    "config is deprecated. Use serin.core.config instead.",
    DeprecationWarning, stacklevel=2
)
