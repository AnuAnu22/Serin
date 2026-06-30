"""Serin messaging subsystem — message processing, context building, response generation."""
from serin.messaging.manager import EnhancedMessageManagerV3
from serin.messaging.response_generator import get_response_natural

__all__ = ["EnhancedMessageManagerV3", "get_response_natural"]
