"""
DEPRECATED: This module has moved to serin.memory.qdrant.
This shim exists for backwards compatibility only. Update your imports.
"""
from serin.memory.qdrant import *  # noqa
from serin.memory.qdrant import QdrantMemorySystem  # explicit
import warnings
warnings.warn(
    "qdrant_memory_system is deprecated. Use serin.memory.qdrant instead.",
    DeprecationWarning, stacklevel=2
)
