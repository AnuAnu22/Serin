"""Production-cipher dump of MessageContext state.

A dump serializes the context into JSON through the SAME encoder the control
panel uses (``make_json_safe`` in ``serin/.../d5_1_state_access.py``) — not a
hand-decorated pretty-printer. Dicts, lists, sets, datetimes, and arbitrary
attrs all coerce exactly the way production coerces them.

Dumps are produced from the ACTUAL final state: either a live ``MessageContext``
(from a real pipeline run) or a recorded boundary snapshot the inspector
captured — never from a freshly-built, unrun context.
"""
from __future__ import annotations

import json
from typing import Any

from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    make_json_safe,
)
from tools.pipeline_inspector.inspector import snapshot_ctx

# Section -> MessageContext field names. Organizational only (drives diff
# grouping); the dump itself is flat production JSON.
SECTIONS: dict[str, tuple[str, ...]] = {
    "INPUT": ("user_id", "username", "channel_id", "guild_id", "raw_content"),
    "DECISION": ("should_respond", "halt_reason", "is_mentioned", "intent", "response_plan"),
    "MEMORY": (
        "memories", "facts", "beliefs", "evidence_memories", "episode_memories",
        "utterance_memories", "recent_messages", "user_profile", "relationships",
    ),
    "PROMPT": (
        "personality_context", "tone_modifier", "system_prompt", "context_block",
        "built_messages",
    ),
    "RESPONSE": ("raw_response", "final_response"),
    "OBSERVABILITY": ("stage_timings", "metadata"),
}


def _production_json(record: dict[str, Any]) -> str:
    return json.dumps(make_json_safe(record), indent=2, default=str)


def dump_context(ctx: MessageContext, *, include_message: bool = False) -> str:
    """Render a live context (e.g. post-run) as production JSON."""
    snap = snapshot_ctx(ctx)
    if not include_message:
        snap.pop("message", None)
    return _production_json(snap)


def dump_snapshot(snapshot: dict[str, Any], *, include_message: bool = False) -> str:
    """Render a recorded boundary snapshot as production JSON."""
    record = dict(snapshot)
    if not include_message:
        record.pop("message", None)
    return _production_json(record)


__all__ = ["SECTIONS", "dump_context", "dump_snapshot"]
