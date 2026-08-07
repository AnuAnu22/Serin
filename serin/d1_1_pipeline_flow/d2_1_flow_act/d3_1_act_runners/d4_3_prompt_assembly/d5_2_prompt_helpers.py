"""
Prompt Assembly Helpers
-----------------------
Standalone helper functions and constants used by PromptAssemblyStage.
Extracted from d4_3_prompt_assembly.py to keep files under 500 lines.
"""
# --- Imports ---
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from serin.d1_4_config_base.d2_3_core_logger import logger

# --- Types ---
# (none)

# --- Constants ---
CONTEXT_BUDGET: dict[str, int] = {
    "facts": 200,
    "beliefs": 100,
    "relationship": 120,
    "belief_evolution": 80,
    "missed": 80,
    "memories": 200,
    "personality": 50,
    "user_profile": 100,
    "history": 500,
}
_TOTAL_BUDGET_CHARS: int = sum(v * 4 for v in CONTEXT_BUDGET.values())

# --- Entry ---


def _time_label(ts_raw: str) -> str:
    """Convert a timestamp string to a human-readable label."""
    if not ts_raw:
        return ""
    try:
        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        delta = datetime.now() - dt
        if delta.days == 0:
            return "[Today] "
        elif delta.days == 1:
            return "[Yesterday] "
        elif delta.days < 7:
            return f"[{delta.days}d ago] "
        return f"[{ts_raw[:10]}] "
    except (ValueError, TypeError):
        logger.exception("Failed to parse timestamp: %s", ts_raw)
        return f"[{ts_raw[:10]}] "


def _confidence_label(conf: float) -> str:
    """Convert a confidence score to a human-readable label."""
    if conf >= 0.9:
        return "[very confident]"
    elif conf >= 0.7:
        return "[confident]"
    elif conf >= 0.4:
        return "[uncertain]"
    return "[low confidence]"


def _fuzz_memories(memories: list[dict[str, Any]], limit: int = 8) -> str:
    """Present memories as fuzzy human impressions, not database records.

    - Recent memories (< 24h): recalled clearly
    - Medium memories (1-7 days): recalled with slight vagueness
    - Old memories (> 7 days): recalled as vague impressions
    - Low confidence facts: recalled with uncertainty language
    """
    if not memories:
        return ""

    # Deduplicate by content hash
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for mem in memories:
        content = mem.get("content", "")
        key = content.strip().lower()[:100]
        if key not in seen and key:
            seen.add(key)
            unique.append(mem)
    memories = unique

    now = datetime.now(UTC)
    lines: list[str] = []

    for mem in memories[:limit]:
        content = mem.get("content", "")
        ts = mem.get("timestamp", "")
        confidence = mem.get("confidence", 1.0)
        username = mem.get("username", mem.get("user_id", "someone"))

        try:
            if isinstance(ts, str):
                mem_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                mem_time = ts
            if mem_time.tzinfo is None:
                mem_time = mem_time.replace(tzinfo=UTC)
            age_hours = (now - mem_time).total_seconds() / 3600
        except Exception:
            logger.debug("Failed to parse memory timestamp: %s", ts)
            age_hours = 999

        if len(content) > 150:
            content = content[:147] + "..."

        if age_hours < 24:
            lines.append(f"- {username} said: \"{content}\"")
        elif age_hours < 168:
            if secrets.randbelow(100) < 30:
                lines.append(f"- {username} mentioned something about: \"{content}\"")
            else:
                lines.append(f"- {username} said (a few days ago): \"{content}\"")
        else:
            if secrets.randbelow(100) < 50:
                words = content.split()
                gist = " ".join(words[:8]) + "..." if len(words) > 8 else content
                lines.append(f"- Something about {username} and: \"{gist}\" (vague memory)")
            else:
                lines.append(f"- {username} talked about (a while ago): \"{content}\"")

        if confidence < 0.5 and secrets.randbelow(100) < 40:
            lines[-1] += " (not sure about this)"

    return "\n".join(lines)


def _affect_context(snap: Any, username: str) -> str:
    """Build a tone directive based on how Serin feels about this user.

    Returns empty string for near-strangers (familiarity < 0.1) so new users
    do not get the old hostile 'You don't really like them' default.
    """
    if snap is None or snap.familiarity < 0.1:
        return ""

    v = snap.valence
    if v > 0.5:
        line = f"You genuinely like {username} and light up a bit when they talk."
    elif v > 0.15:
        line = f"You're warm toward {username}."
    elif v < -0.5:
        line = f"You find {username} grating. You're curt and don't go out of your way for them."
    elif v < -0.15:
        line = f"You're a bit wary of {username}."
    else:
        line = f"You feel neutral about {username}."

    if snap.impression:
        line += f" Your current impression: {snap.impression}"

    return line


def _belief_evolution_context(memory_system: Any, query: str) -> str:
    """Find beliefs that recently changed and surface them naturally."""
    if not memory_system:
        return ""
    try:
        beliefs = memory_system.get_relevant_beliefs(query=query, limit=5)
        if not beliefs:
            return ""

        evolved = []
        for belief in beliefs:
            state = belief.get("state", "")
            content = belief.get("content", "")
            confidence = belief.get("confidence", 0.5)

            if state == "CONTESTED" and confidence < 0.5:
                evolved.append(
                    f"You used to believe \"{content}\" but now you're not so sure. "
                    f"You might mention this uncertainty naturally."
                )
            elif state == "SUPERSEDED":
                evolved.append(
                    f"You used to think \"{content}\" but your opinion has changed. "
                    f"You can reference how your thinking evolved."
                )
            elif state == "SUPPORTED" and confidence > 0.8:
                evolved.append(
                    f"You strongly believe \"{content}\". "
                    f"This is a core opinion you hold confidently."
                )

        if not evolved:
            return ""
        return "\n".join(evolved[:3])
    except Exception as exc:
        logger.debug("Failed to build belief evolution context: %s", exc)
        return ""


def _facts_context(memory_system: Any, user_id: str) -> str:
    """Build a natural description of known facts about this user from the Bayesian engine."""
    if not memory_system or not user_id:
        return ""
    try:
        engine = getattr(memory_system, "belief_engine", None)
        if engine is None:
            return ""
        facts = engine.get_facts_for_user(user_id, limit=5)
        if not facts:
            return ""
        lines: list[str] = []
        for f in facts:
            label = engine.get_confidence_label(f["belief"], f["variance"])
            state = f.get("state", "PENDING")
            if state == "SUPERSEDED":
                continue
            elif state == "CONTESTED":
                lines.append(f"- {f['claim']} ({label}, but someone disagreed)")
            else:
                lines.append(f"- {f['claim']} ({label})")
        if not lines:
            return ""
        return "Things you know about this person:\n" + "\n".join(lines)
    except Exception:
        return ""


def _truncate_to_budget(text: str, max_tokens: int) -> str:
    """Truncate text to fit within token budget."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."

# --- Core ---
# (none — these are standalone helpers, not class methods)

# --- Helpers ---
# (none)

# --- Errors ---
# (none)
