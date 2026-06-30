"""
DEPRECATED: Stages have been extracted to serin.messaging.stages/ directory.
This shim exists for backwards compatibility only. Update your imports.
"""
from serin.messaging.stages import *  # noqa: F401, F403
from serin.messaging.stages import PipelineStage  # explicit
from serin.messaging.context import MessageContext
import warnings
warnings.warn(
    "serin.messaging.stages (monolithic) is deprecated. "
    "Use serin.messaging.stages.<stage_name> for individual stages.",
    DeprecationWarning, stacklevel=2
)
