"""Message perception — evidence detection, board parsing, personality analysis.

This package is the folder form of the former ``perception.py`` (Rule 2: a file
over 500 lines becomes a folder). Its public API is re-exported here so every
existing import path (``from ...core.perception import ...``) keeps working.
Backward-compatible private aliases are preserved for any dynamic binding.
"""

from .d5_1_perception_board import derive_from_board, parse_board
from .d5_2_perception_classify import (
    EVIDENCE_PATTERNS,
    detect_evidence,
    perceive_message,
)
from .d5_3_perception_personality import (
    analyze_personality,
    detect_topic,
    get_emotional_tone,
)
from .d5_4_perception_profile import (
    MessageManagerV3,
    get_memory_stats,
    get_user_profile,
)
from .d5_5_perception_result import (
    ARGUMENT_KEYWORDS,
    CLAIM_PATTERNS,
    JOKE_MARKERS,
    SARCASM_MARKERS,
    PerceptionResult,
)

# Backward-compatible private aliases (declared in this module, not imported)
_detect_evidence = detect_evidence
_perceive_message = perceive_message
_parse_board = parse_board
_derive_from_board = derive_from_board
_analyze_personality = analyze_personality
_get_emotional_tone = get_emotional_tone
_detect_topic = detect_topic
_ARGUMENT_KEYWORDS = ARGUMENT_KEYWORDS
_CLAIM_PATTERNS = CLAIM_PATTERNS
_EVIDENCE_PATTERNS = EVIDENCE_PATTERNS
_JOKE_MARKERS = JOKE_MARKERS
_SARCASM_MARKERS = SARCASM_MARKERS

__all__ = [
    "PerceptionResult",
    "EVIDENCE_PATTERNS",
    "CLAIM_PATTERNS",
    "SARCASM_MARKERS",
    "JOKE_MARKERS",
    "ARGUMENT_KEYWORDS",
    "detect_evidence",
    "perceive_message",
    "parse_board",
    "derive_from_board",
    "analyze_personality",
    "get_emotional_tone",
    "detect_topic",
    "get_user_profile",
    "get_memory_stats",
    "MessageManagerV3",
]
