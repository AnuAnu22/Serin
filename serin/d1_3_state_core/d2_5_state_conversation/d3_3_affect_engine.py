"""UserAffectEngine — per-user sentiment valence, familiarity, and LLM impressions.

Tracks how Serin feels about individual users over time. Valence is driven by
per-message sentiment (tiny increments, ±0.05 per message) and decays toward
neutral with a 72-hour half-life. Periodic background LLM impressions add a
qualitative note that gets injected into the prompt.

Store is duck-typed / DI'd — never imported here (depth DAG compliance).
This module sits at depth 3; callers at depth 4+ inject the store.
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass
from typing import Any

from serin.d1_4_config_base.d2_3_core_logger import logger

# --- Types ---

@dataclass
class AffectSnapshot:
    """Immutable read-only view of a user's current affect state."""
    valence: float       # [-1, 1], 0 = neutral
    familiarity: float   # [0, 1), derived from message count
    impression: str | None  # latest LLM impression text, or None

# --- Constants ---

DECAY_HALF_LIFE_S: float = 72.0 * 3600.0   # 72 hours → half-life
SENTIMENT_GAIN: float = 0.05                # per-message valence nudge
IMPRESSION_DELTA_CAP: float = 0.20          # max single impression adjustment
IMPRESSION_TEXT_MAX_CHARS: int = 200
_FAMILIARITY_SCALE: float = 50.0            # count at which familiarity ≈ 0.63

# Relationship buckets derived from (valence, familiarity), used to bias
# per-user mood at write time. With steady per-message sentiment of
# SENTIMENT_GAIN * avg_sentiment, |valence| reaches ~0.3 within a handful of
# messages, so "enemy" is reachable quickly; "friend" requires both real
# familiarity (>=0.5 ~ 35+ messages) and sustained positivity.
_STRANGER_FAMILIARITY_THRESHOLD: float = 0.1
_ENEMY_VALENCE_THRESHOLD: float = -0.3
_FRIEND_FAMILIARITY_THRESHOLD: float = 0.5
_FRIEND_VALENCE_THRESHOLD: float = 0.3

_NEUTRAL = AffectSnapshot(valence=0.0, familiarity=0.0, impression=None)

# --- Helpers ---

def _decayed_valence(v: float, last_ts: float, now: float) -> float:
    """Exponential decay toward 0 with half-life DECAY_HALF_LIFE_S."""
    return v * math.pow(0.5, (now - last_ts) / DECAY_HALF_LIFE_S)


def _familiarity(count: int) -> float:
    """Map interaction count to [0, 1) via 1 - exp(-count / scale)."""
    if count <= 0:
        return 0.0
    return 1.0 - math.exp(-count / _FAMILIARITY_SCALE)


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def relationship_category(valence: float, familiarity: float) -> str:
    """Map (valence, familiarity) to a coarse relationship bucket.

    Order matters: a user can be both high-familiarity and badly valenced,
    so stranger (low familiarity) is the base case and enemy wins over
    friend when valence is negative enough. Returns one of:
    ``stranger`` / ``enemy`` / ``friend`` / ``acquaintance``.
    """
    if familiarity < _STRANGER_FAMILIARITY_THRESHOLD:
        return "stranger"
    if valence < _ENEMY_VALENCE_THRESHOLD:
        return "enemy"
    if familiarity >= _FRIEND_FAMILIARITY_THRESHOLD and valence > _FRIEND_VALENCE_THRESHOLD:
        return "friend"
    return "acquaintance"

# --- Entry ---

class UserAffectEngine:
    """Per-user affect state with write-through cache.

    Usage:
        engine = UserAffectEngine(store)  # store injected by caller
        snap = engine.snapshot_cached(user_id)  # sync, neutral on miss
        await engine.record_sentiment(user_id, sentiment_score)
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        # In-memory cache: user_id → AffectSnapshot (pre-computed from DB row).
        self._cache: dict[str, AffectSnapshot] = {}
        # Raw rows (including valence_updated, familiarity_count) for write-back.
        self._rows: dict[str, dict[str, Any]] = {}

    # --- Core ---

    def snapshot_cached(self, user_id: str) -> AffectSnapshot:
        """Return cached snapshot, or neutral default on miss.

        On a cache miss a background load is scheduled so the next call
        after the event-loop tick will have the DB value. The one-message
        lag on restart is acceptable (vision: Serin is imperfect).
        """
        snap = self._cache.get(user_id)
        if snap is None:
            # Best-effort background load so the next tick has the DB value.
            # If there is no running event loop in this thread (sync context,
            # startup before the bot loop exists, or a sync test), skip it -
            # a one-message lag on a cache miss is acceptable per the vision
            # (Serin is imperfect). get_running_loop (not the deprecated
            # get_event_loop) keeps scheduling on pytest-asyncio's per-test
            # loop instead of leaking loop state across tests.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return _NEUTRAL
            loop.call_soon(
                lambda: asyncio.ensure_future(self._load_from_store(user_id))
            )
            return _NEUTRAL
        return snap

    async def record_sentiment(self, user_id: str, sentiment: float) -> None:
        """Update valence from one message's sentiment score (± SENTIMENT_GAIN)."""
        now = time.time()
        row = self._rows.get(user_id)
        if row is None:
            # Try DB
            try:
                from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
                    get_user_affect,
                )
                row = get_user_affect(self._store, user_id)
            except Exception as e:
                logger.debug("affect store read failed for %s: %s", user_id, e)
        if not row:
            row = {"valence": 0.0, "valence_updated": now, "familiarity_count": 0,
                   "impression_text": None, "impression_updated": None, "since_impression": 0}

        old_v = _decayed_valence(row["valence"], row["valence_updated"], now)
        new_v = _clamp(old_v + SENTIMENT_GAIN * sentiment)
        new_count = row["familiarity_count"] + 1

        row["valence"] = new_v
        row["valence_updated"] = now
        row["familiarity_count"] = new_count
        self._rows[user_id] = row
        self._cache[user_id] = AffectSnapshot(
            valence=new_v,
            familiarity=_familiarity(new_count),
            impression=row.get("impression_text"),
        )

        try:
            from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
                upsert_user_affect,
            )
            upsert_user_affect(
                self._store, user_id,
                valence=new_v,
                valence_updated=now,
                familiarity_count=new_count,
            )
        except Exception as e:
            logger.debug("affect write-through failed for %s: %s", user_id, e)

    async def apply_impression(self, user_id: str, text: str, delta: float) -> None:
        """Apply an LLM impression: adjust valence, store text, reset counter."""
        now = time.time()
        row = self._rows.get(user_id, {"valence": 0.0, "valence_updated": now,
                                       "familiarity_count": 0, "impression_text": None,
                                       "impression_updated": None, "since_impression": 0})
        clamped_delta = _clamp(delta, -IMPRESSION_DELTA_CAP, IMPRESSION_DELTA_CAP)
        old_v = _decayed_valence(row["valence"], row["valence_updated"], now)
        new_v = _clamp(old_v + clamped_delta)
        impression_stored = text[:IMPRESSION_TEXT_MAX_CHARS]

        row["valence"] = new_v
        row["valence_updated"] = now
        row["impression_text"] = impression_stored
        row["impression_updated"] = now
        row["since_impression"] = 0
        self._rows[user_id] = row
        self._cache[user_id] = AffectSnapshot(
            valence=new_v,
            familiarity=_familiarity(row["familiarity_count"]),
            impression=impression_stored,
        )

        try:
            from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
                upsert_user_affect,
            )
            upsert_user_affect(
                self._store, user_id,
                valence=new_v,
                valence_updated=now,
                familiarity_count=row["familiarity_count"],
                impression_text=impression_stored,
                impression_updated=now,
                since_impression=0,
            )
        except Exception as e:
            logger.debug("affect impression write-through failed for %s: %s", user_id, e)

    # --- Helpers ---

    async def _load_from_store(self, user_id: str) -> None:
        """Background load of a user's affect row into cache."""
        try:
            from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
                get_user_affect,
            )
            row = get_user_affect(self._store, user_id)
            if row is None:
                return
            now = time.time()
            v = _decayed_valence(row["valence"], row["valence_updated"], now)
            self._rows[user_id] = row
            self._cache[user_id] = AffectSnapshot(
                valence=v,
                familiarity=_familiarity(row["familiarity_count"]),
                impression=row.get("impression_text"),
            )
        except Exception as e:
            logger.debug("affect background load failed for %s: %s", user_id, e)

    def build_impression_prompt(
        self, username: str, messages: list[str], valence: float
    ) -> str:
        """Build the LLM prompt asking for a qualitative impression of the user."""
        msgs_text = "\n".join(f"- {m}" for m in messages[-30:])
        return (
            f"You are Serin. Privately, candidly, in 1-2 sentences: what's your "
            f"honest impression of {username} based on these recent messages? "
            f"Their vibe, how they treat you and others.\n"
            f"Current feeling: {valence:+.2f} (-1 dislike .. +1 like).\n"
            f"Recent messages:\n{msgs_text}\n\n"
            f"Respond ONLY with JSON: "
            f'{{\"impression\": \"<1-2 sentences>\", \"valence_delta\": <float -0.2 to 0.2>}}'
        )

    @staticmethod
    def parse_impression(raw: str) -> tuple[str, float] | None:
        """Parse LLM impression JSON. Returns (text, delta) or None on bad output."""
        try:
            data = json.loads(raw)
            impression = data.get("impression", "")
            delta = data.get("valence_delta")
            if not impression or delta is None:
                return None
            return str(impression)[:IMPRESSION_TEXT_MAX_CHARS], float(delta)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
