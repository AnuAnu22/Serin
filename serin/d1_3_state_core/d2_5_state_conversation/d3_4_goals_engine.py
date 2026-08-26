"""Self-generated goal formation + revision machinery (d1_3 state layer).

The cognitive-state half of the goals engine: sits next to the dynamics and
affect engines and owns WHEN goals are formed/reviewed/dropped and HOW much
they are pursued. Storage lives behind ``d6_1_goals_store`` (duck-typed
store contract; edge-B function-scoped imports).

Doctrine (SERIN_VISION "Growth", creator directive): MACHINERY ONLY. This
module decides thresholds, decays salience, schedules reviews, and parses
well-formed LLM output — it never curates, sanitizes, or templates the
CONTENT of a goal statement. Whatever statement survives JSON validation is
stored verbatim.
"""
# --- Imports ---
from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("serin")

# --- Types ---
# (none)

# --- Constants ---
#: Minimum seconds between two reviews of the same goal (maintenance cadence).
REVIEW_INTERVAL_S: float = 6 * 3600.0
#: At most this many live goals before formation stops proposing new ones.
MAX_ACTIVE_GOALS: int = 5
#: At most one new goal per maintenance cycle (slow burn, not spam).
FORMATION_MAX_PER_CYCLE: int = 1
#: Salience below this after decay means the goal quietly dies.
SALIENCE_DROP_FLOOR: float = 0.05
#: Per-review decay for pursued (FORMING/ACTIVE) goals.
DECAY_ACTIVE_PER_REVIEW: float = 0.03
#: Per-review decay for parked (PAUSED) goals — they fade faster.
DECAY_PAUSED_PER_REVIEW: float = 0.08
#: A goal statement longer than this is treated as malformed output.
MAX_STATEMENT_CHARS: int = 600
#: Fewer batch lines than this and there is nothing to form goals FROM.
MIN_BATCH_LINES_FOR_FORMATION: int = 5
#: Pursuit snapshot floor — low-drive goals do not reach the pipeline.
PURSUIT_MIN_SALIENCE: float = 0.15

# --- Helpers ---


def _clamp01(value: float) -> float:
    """Clamp to [0.0, 1.0]."""
    return max(0.0, min(1.0, float(value)))


def parse_formation(raw_response: str) -> tuple[str, float] | None:
    """Parse the forming LLM's reply into (verbatim_statement, salience).

    Accepts a bare JSON object or one wrapped in a code fence. Returns None
    for anything malformed. The statement is NOT rewritten — only validated
    (non-empty, within the length guard); salience is clamped.
    """
    text = str(raw_response).strip()
    if "```" in text:
        # Strip code fences wherever they sit (leading, trailing, or both):
        # keep only the content BETWEEN the first and second fence marks.
        parts = text.split("```")
        inner = [p for p in parts[1:-1] if p.strip()] or \
            ([parts[-1]] if len(parts) == 2 else [])
        text = (inner[0] if inner else text).strip()
        # Drop a leading language tag like "json" from the first fence line.
        first_line, sep, rest = text.partition("\n")
        if sep and not first_line.lstrip().startswith("{"):
            text = rest.strip()
    try:
        obj: Any = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    statement = obj.get("statement")
    salience_raw = obj.get("salience", 0.5)
    if not isinstance(statement, str):
        return None
    statement = statement.strip()
    if not statement or len(statement) > MAX_STATEMENT_CHARS:
        return None
    try:
        salience = _clamp01(float(salience_raw))
    except (TypeError, ValueError):
        salience = 0.5
    return statement, salience


# --- Entry ---


class GoalsEngine:
    """Owns goal formation thresholds, review decay, and pursuit reads."""

    def __init__(self, memory: Any) -> None:
        """``memory`` is duck-typed: anything with ``.conn`` (the core store)."""
        self.memory = memory

    # -- formation ---------------------------------------------------------

    def build_formation_prompt(self, recent_lines: list[str],
                               existing_statements: list[str]) -> str:
        """Prompt the supporting LLM to propose ONE new goal, or nothing."""
        existing_block = "\n".join(
            f"- {s}" for s in existing_statements[:MAX_ACTIVE_GOALS])
        convo_block = "\n".join(recent_lines[-20:])
        return (
            "You are Serin, reflecting on your recent conversations. Based on "
            "this material, decide whether a NEW personal goal of yours has "
            "emerged - something you actually want to do, explore, build, "
            "understand, or pursue. It can be about anything at all. Reply "
            "with ONLY a JSON object, no commentary:\n"
            '{"statement": "<your goal in first person, concrete>", '
            '"salience": <0.0-1.0 how strongly you want it now>}\n'
            "If nothing genuinely pulls at you, reply "
            ' {"statement": "", "salience": 0.0}.\n\n'
            "Goals you already hold:\n"
            f"{existing_block or '- (none yet)'}\n\n"
            "Recent conversations:\n"
            f"{convo_block}\n"
        )

    def form_goal(self, statement: str, salience: float,
                  provenance: str, detail: str = "",
                  parent_goal_id: int | None = None) -> int:
        """Create one FORMING goal + its `formed` evidence entry."""
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
            d6_1_goals_store,
        )

        gid = d6_1_goals_store.create_goal(
            self.memory, statement, salience,
            provenance=provenance, parent_goal_id=parent_goal_id)
        if gid > 0:
            d6_1_goals_store.add_goal_evidence(
                self.memory, gid, "formed",
                detail=detail or provenance, source="background_llm")
            logger.info("goal.formed id=%s salience=%.2f", gid, salience)
        return gid

    # -- review --------------------------------------------------------------

    def review_due(self, older_than_s: float = REVIEW_INTERVAL_S,
                   limit: int = 10) -> int:
        """Decay + re-stamp stale goals; drop ones that hit the floor.

        Returns the number of goals reviewed. Deterministic: pure arithmetic
        on stored salience, no randomness anywhere.
        """
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
            d6_1_goals_store,
        )

        due = d6_1_goals_store.get_goals_due_review(
            self.memory, older_than_s=older_than_s, limit=limit)
        reviewed = 0
        for row in due:
            status = str(row.get("status"))
            salience = float(row.get("salience", 0.0))
            decay = (DECAY_PAUSED_PER_REVIEW if status == "PAUSED"
                     else DECAY_ACTIVE_PER_REVIEW)
            new_salience = _clamp01(salience - decay)
            gid = int(row["id"])
            if new_salience < SALIENCE_DROP_FLOOR:
                # Quiet death: the drive faded below the floor.
                d6_1_goals_store.update_goal_status(
                    self.memory, gid, "DROPPED")
                d6_1_goals_store.add_goal_evidence(
                    self.memory, gid, "auto_dropped",
                    detail=f"salience decayed {salience:.2f} -> floor",
                    source="review")
                logger.info("goal.auto_dropped id=%s", gid)
            else:
                d6_1_goals_store.update_goal_status(
                    self.memory, gid, status,
                    salience_delta=-decay)
                d6_1_goals_store.add_goal_evidence(
                    self.memory, gid, "reviewed",
                    detail=f"salience {salience:.2f} -> {new_salience:.2f}",
                    source="review")
            reviewed += 1
        return reviewed

    def promote_ready(self, max_promote: int = 3) -> int:
        """Promote long-standing FORMING goals to ACTIVE.

        A FORMING goal whose row has survived one review window (i.e. it now
        carries a last_reviewed_at) counts as stable enough to pursue.
        """
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
            d6_1_goals_store,
        )

        promoted = 0
        for row in d6_1_goals_store.get_active_goals(
                self.memory, min_salience=0.0, limit=50):
            if promoted >= max_promote:
                break
            if (str(row.get("status")) == "FORMING"
                    and row.get("last_reviewed_at") is not None):
                if d6_1_goals_store.update_goal_status(
                        self.memory, int(row["id"]), "ACTIVE"):
                    d6_1_goals_store.add_goal_evidence(
                        self.memory, int(row["id"]), "activated",
                        detail="survived first review", source="review")
                    promoted += 1
        return promoted

    # -- pursuit ---------------------------------------------------------------

    def pursuit_snapshot(self, limit: int = 3) -> list[dict[str, Any]]:
        """Top-salience live goals above the pursuit floor (pipeline order)."""
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
            d6_1_goals_store,
        )

        return d6_1_goals_store.get_active_goals(
            self.memory, min_salience=PURSUIT_MIN_SALIENCE, limit=limit)

    def touch_on_mention(self, fragment: str) -> int:
        """Reinforce goals whose statement overlaps `fragment` (lowercase).

        Called when conversation content overlaps a held goal: the drive
        strengthens because reality keeps brushing it. Returns count bumped.
        """
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
            d6_1_goals_store,
        )

        frag = fragment.lower().strip()
        if len(frag) < 12:  # too short to mean anything
            return 0
        bumped = 0
        for row in self.pursuit_snapshot(limit=8):
            words = [w for w in frag.split() if len(w) > 4]
            stmt_words = {
                w.strip('\".,!?\'()').lower()
                for w in str(row["statement"]).split()
            }
            overlap = sum(1 for w in words if w in stmt_words)
            if overlap >= 2:
                if d6_1_goals_store.bump_goal_salience(
                        self.memory, int(row["id"]), 0.05):
                    d6_1_goals_store.add_goal_evidence(
                        self.memory, int(row["id"]), "reinforced",
                        detail=f"conversation overlap ({overlap} tokens)",
                        source="pipeline")
                    bumped += 1
        return bumped

    def stats(self) -> dict[str, Any]:
        """Histogram + top pursuit rows for panel/logging consumers."""
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage.d6_1_goals_store import (
            count_goals_by_status,
        )

        return {
            "counts": count_goals_by_status(self.memory),
            "pursuit": [
                {"id": int(r["id"]),
                 "statement": str(r["statement"]),
                 "status": str(r["status"]),
                 "salience": float(r["salience"])}
                for r in self.pursuit_snapshot(limit=5)
            ],
            "review_interval_s": REVIEW_INTERVAL_S,
            "checked_at": time.time(),
        }

# --- Helpers ---
# (none)

# --- Errors ---
# (none)
