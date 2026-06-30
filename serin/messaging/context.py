"""
serin.messaging.context
-----------------------
MessageContext is the data envelope that flows through the message pipeline.
Every stage reads from it and writes to it. No stage has side effects
outside of what it writes into the context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineDeps:
    """All external dependencies injected into the pipeline."""
    memory: Any
    context_builder: Any
    bot_personality: Any
    response_controller: Any
    personality: Any
    voice_tracker: Any
    conversation_analyzer: Any
    analyzer: Any  # SentimentIntensityAnalyzer
    pending_visual_contexts: Dict[int, str]
    active_search: Optional[Any]
    voice_action_decider: Optional[Any]
    voice_action_callback: Optional[Any]
    mention_translator: Any
    current_state: Dict[str, Any]
    stats: Dict[str, int]
    last_bot_response: Optional[str]
    last_bot_response_channel: Optional[str]


@dataclass
class MessageContext:
    """Mutable context passed through each pipeline stage."""

    # Input (set at pipeline entry, never mutated)
    batch: list
    bot_mentioned: bool = False

    # Derived fields
    channel: Any = None
    user_messages: list = field(default_factory=list)
    is_instruction: bool = False
    primary_user_id: str = ""

    # Memory retrieval
    context: dict = field(default_factory=dict)
    formatted_context: str = ""

    # Conversation analysis
    conv_analysis: dict = field(default_factory=dict)
    preference_context: Optional[str] = None
    voice_info: Optional[dict] = None
    resolved_message: str = ""
    tone_modifier: str = ""
    length_analysis: dict = field(default_factory=dict)
    fatigue_level: float = 0.0
    detected_topic: Optional[str] = None

    # Active search
    active_search_results: list = field(default_factory=list)

    # Response
    response: Optional[str] = None
    should_halt: bool = False

    # Observability
    stage_timings: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
