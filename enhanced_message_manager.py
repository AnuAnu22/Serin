"""
DEPRECATED: This module has moved to serin.messaging.manager.
This shim exists for backwards compatibility only. Update your imports.
"""
from serin.messaging.manager import *  # noqa
from serin.messaging.manager import EnhancedMessageManagerV3
import warnings
warnings.warn(
    "enhanced_message_manager is deprecated. Use serin.messaging.manager instead.",
    DeprecationWarning, stacklevel=2
)
