"""Personality, emotional-tone, and topic detection for perceived messages."""

from __future__ import annotations

from typing import Any


def analyze_personality(self: Any, user_id: str, content: str) -> list[str]:
    """Analyze message and update personality traits. Returns detected traits."""
    traits: list[str] = []
    interests: list[str] = []
    content_lower = content.lower()

    if any(w in content_lower for w in [            "lol", "haha", "lmao"]):
        traits.append("humorous")
    if any(w in content_lower for w in ["thanks", "please", "sorry"]):
        traits.append("polite")
    if len(content) > 200:
        traits.append("verbose")
    elif len(content) < 20:
        traits.append("concise")
    if content.count("!") > 2:
        traits.append("enthusiastic")

    interest_keywords = {
        "gaming": ["game", "play", "steam", "xbox", "ps5"],
        "anime": ["anime", "manga", "weeb"],
        "music": ["song", "music", "band", "album"],
        "tech": ["code", "programming", "ai", "computer"],
        "art": ["draw", "art", "paint", "sketch"],
    }
    for interest, keywords in interest_keywords.items():
        if any(kw in content_lower for kw in keywords):
            interests.append(interest)

    if traits or interests:
        self.memory.update_user_traits(user_id, traits, interests)

    return traits


def get_emotional_tone(self: Any, sentiment_score: float) -> str:
    """Convert sentiment score to emotional tone"""
    if sentiment_score > 0.5:
        return "happy"
    elif sentiment_score > 0.2:
        return "positive"
    elif sentiment_score < -0.5:
        return "sad"
    elif sentiment_score <= -0.2:
        return "negative"
    return "neutral"


def detect_topic(self: Any, content: str) -> str | None:
    """Simple topic detection"""
    content_lower = content.lower()
    topics = {
        "gaming": ["game", "gaming", "play", "steam", "xbox", "ps5", "nintendo"],
        "anime": ["anime", "manga", "weeb"],
        "music": ["song", "music", "band", "album", "spotify"],
        "food": ["food", "eat", "cooking", "recipe", "restaurant"],
        "work": ["work", "job", "boss", "office", "meeting"],
        "school": ["school", "class", "homework", "exam", "teacher"],
        "movies": ["movie", "film", "cinema", "netflix"],
        "sports": ["sport", "football", "basketball", "soccer", "gym"],
    }
    for topic, keywords in topics.items():
        if any(kw in content_lower for kw in keywords):
            return topic
    return None
