"""Bayesian Belief Dynamics Engine.

Bayesian update of fact confidence using log-odds space,
Kalman-inspired variance tracking, temporal decay toward
uncertainty, claim-hash deduplication, and a fact state machine.
"""
from __future__ import annotations

import hashlib
import math
import sqlite3
from datetime import UTC, datetime
from typing import Any

from serin.d1_3_state_core.d2_5_core_logger import logger


class BayesianBeliefEngine:
    """Manages fact storage, Bayesian updates, temporal decay, and retrieval."""

    SOURCE_WEIGHTS: dict[str, float] = {
        "self_confirm": 5.0,
        "self_contradict": 0.15,
        "other_confirm": 2.0,
        "other_contradict": 0.5,
        "reported": 1.8,
        "inferred": 1.3,
        "corroboration": 2.5,
    }
    HALF_LIFE_DAYS: float = 30.0
    PROCESS_NOISE: float = 0.01
    MIN_BELIEF: float = 0.01
    MAX_BELIEF: float = 0.99

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ── Math helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _log_odds(p: float) -> float:
        p = max(BayesianBeliefEngine.MIN_BELIEF, min(BayesianBeliefEngine.MAX_BELIEF, p))
        return math.log(p / (1.0 - p))

    @staticmethod
    def _sigmoid(lo: float) -> float:
        if lo > 20:
            return BayesianBeliefEngine.MAX_BELIEF
        if lo < -20:
            return BayesianBeliefEngine.MIN_BELIEF
        return 1.0 / (1.0 + math.exp(-lo))

    def _decay_rate(self) -> float:
        return math.log(2.0) / self.HALF_LIFE_DAYS

    # ── Core operations ──────────────────────────────────────────────────

    def apply_temporal_decay(self, fact_id: int) -> dict[str, float]:
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT belief, variance, last_confirmed FROM facts WHERE id = ?",
            (fact_id,),
        ).fetchone()
        if not row:
            return {"belief": 0.5, "variance": 0.25, "confidence": 0.5, "days_since": 0}

        belief, variance, last_confirmed = row["belief"], row["variance"], row["last_confirmed"]

        now = datetime.now(UTC)
        try:
            if isinstance(last_confirmed, str):
                last_dt = datetime.fromisoformat(last_confirmed.replace("Z", "+00:00"))
            else:
                last_dt = last_confirmed
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.exception("apply_temporal_decay: bad timestamp for fact %s", fact_id)
            last_dt = now

        days_since = max(0.0, (now - last_dt).total_seconds() / 86400.0)

        decayed = 0.5 + (belief - 0.5) * math.exp(-self._decay_rate() * days_since)
        decayed = max(self.MIN_BELIEF, min(self.MAX_BELIEF, decayed))

        var_growth = variance + self.PROCESS_NOISE * days_since
        var_growth = max(0.001, min(0.25, var_growth))

        cursor.execute(
            "UPDATE facts SET belief = ?, variance = ?, log_odds = ? WHERE id = ?",
            (decayed, var_growth, self._log_odds(decayed), fact_id),
        )
        self.conn.commit()

        return {"belief": decayed, "variance": var_growth, "confidence": 1.0 - var_growth, "days_since": days_since}

    @staticmethod
    def _map_source(source_type: str, observation_type: str = "confirm") -> str:
        """Map generic source_type to a SOURCE_WEIGHTS key."""
        mapped: dict[str, str] = {
            "self_confirm": "self_confirm",
            "self_contradict": "self_contradict",
            "other_confirm": "other_confirm",
            "other_contradict": "other_contradict",
        }
        if source_type in mapped:
            return source_type
        if source_type in ("self", "user_claim", "user"):
            return "self_confirm" if observation_type in ("confirm", "corroborate") else "self_contradict"
        if source_type in ("other", "reported"):
            return "other_confirm" if observation_type in ("confirm", "corroborate") else "other_contradict"
        return source_type

    def observe(
        self,
        fact_id: int,
        observer_id: str | None = None,
        observation_type: str = "confirm",
        source_type: str = "self",
    ) -> dict[str, Any]:
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT belief, variance, state FROM facts WHERE id = ?",
            (fact_id,),
        ).fetchone()
        if not row:
            return {"belief": 0.5, "variance": 0.25, "state": "PENDING"}

        belief, variance, state = row["belief"], row["variance"], row["state"]

        # Map source_type to weight key, then look up LR
        weight_key = self._map_source(source_type, observation_type)
        lr = self.SOURCE_WEIGHTS.get(weight_key, 1.0)
        if lr < 0.001:
            lr = 0.001

        # Bayesian update in log-odds space
        prior_lo = self._log_odds(belief)
        likelihood_lo = math.log(lr)
        posterior_lo = prior_lo + likelihood_lo
        posterior_belief = self._sigmoid(posterior_lo)

        # Kalman-inspired variance update
        obs_var = 1.0 / (lr + 1e-6)
        kalman_gain = variance / (variance + obs_var + 1e-12)
        posterior_variance = (1.0 - kalman_gain) * variance + self.PROCESS_NOISE
        posterior_variance = max(0.001, min(0.25, posterior_variance))

        now = datetime.now(UTC).isoformat()

        # State machine
        new_state = state
        if observation_type in ("confirm", "corroborate"):
            if state == "PENDING":
                new_state = "SUPPORTED"
            elif state == "CONTESTED" and posterior_belief > 0.6:
                new_state = "SUPPORTED"
        elif observation_type in ("contradict", "challenge"):
            if state == "PENDING":
                new_state = "CONTESTED"
            elif state == "SUPPORTED" and posterior_belief < 0.4:
                new_state = "CONTESTED"

        # Build column updates
        set_parts = [
            "belief = ?",
            "variance = ?",
            "log_odds = ?",
            "state = ?",
            "last_confirmed = ?",
        ]
        set_vals: list[Any] = [
            posterior_belief,
            posterior_variance,
            self._log_odds(posterior_belief),
            new_state,
            now,
        ]

        if observation_type in ("contradict", "challenge"):
            set_parts.append("last_challenged = ?")
            set_vals.append(now)

        set_parts.append("observation_count = observation_count + 1")
        if observation_type == "corroborate":
            set_parts.append("corroboration_count = corroboration_count + 1")

        set_vals.append(fact_id)
        cursor.execute(
            f"UPDATE facts SET {', '.join(set_parts)} WHERE id = ?",
            set_vals,
        )
        self.conn.commit()

        # Log the observation
        cursor.execute(
            "INSERT INTO fact_observations (fact_id, observer_id, observation_type, source_type, weight) "
            "VALUES (?, ?, ?, ?, ?)",
            (fact_id, observer_id, observation_type, weight_key, lr),
        )
        self.conn.commit()

        return {"belief": posterior_belief, "variance": posterior_variance, "state": new_state}

    def store_fact(
        self,
        subject_id: str,
        subject_name: str,
        claim: str,
        category: str = "observation",
        source: str = "",
        source_type: str = "user_claim",
        initial_confidence: float = 0.4,
    ) -> int:
        claim_hash = hashlib.sha256(f"{subject_id}:{claim.lower().strip()}".encode()).hexdigest()[:16]
        cursor = self.conn.cursor()

        existing = cursor.execute(
            "SELECT id, belief, variance FROM facts WHERE claim_hash = ?",
            (claim_hash,),
        ).fetchone()

        if existing:
            existing_id: int = int(existing["id"])
            self.observe(
                fact_id=existing_id,
                observer_id=subject_id,
                observation_type="corroborate",
                source_type="corroboration",
            )
            return existing_id

        log_odds_val = self._log_odds(max(self.MIN_BELIEF, min(self.MAX_BELIEF, initial_confidence)))
        variance = 0.25 * (1.0 - initial_confidence) + 0.01
        variance = max(0.001, min(0.25, variance))
        now = datetime.now(UTC).isoformat()

        cursor.execute(
            "INSERT INTO facts "
            "(subject_id, subject_name, claim, category, belief, variance, log_odds, "
            "first_observed, last_confirmed, primary_source, source_type, state, claim_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (subject_id, subject_name, claim, category, initial_confidence, variance, log_odds_val,
             now, now, source, source_type, "PENDING", claim_hash),
        )
        self.conn.commit()

        raw_id: Any = cursor.lastrowid
        new_id: int = raw_id if raw_id is not None else 0

        # Log initial observation
        cursor.execute(
            "INSERT INTO fact_observations (fact_id, observer_id, observation_type, source_type, weight) "
            "VALUES (?, ?, ?, ?, ?)",
            (new_id, subject_id, "confirm", source_type, self.SOURCE_WEIGHTS.get(source_type, 1.0)),
        )
        self.conn.commit()

        return new_id

    # ── Retrieval ─────────────────────────────────────────────────────────

    def get_facts_for_user(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()
        rows = cursor.execute(
            "SELECT id, subject_id, subject_name, claim, category, belief, variance, "
            "log_odds, state, observation_count, corroboration_count, contradiction_count "
            "FROM facts WHERE subject_id = ? AND is_active = 1 "
            "ORDER BY last_confirmed DESC",
            (user_id,),
        ).fetchall()

        if not rows:
            return []

        results: list[dict[str, Any]] = []
        for row in rows:
            decayed = self.apply_temporal_decay(row["id"])
            results.append({
                "_fact_id": row["id"],
                "subject_id": row["subject_id"],
                "subject_name": row["subject_name"],
                "claim": row["claim"],
                "category": row["category"],
                "belief": decayed["belief"],
                "variance": decayed["variance"],
                "state": row["state"],
                "observation_count": row["observation_count"],
                "corroboration_count": row["corroboration_count"],
                "contradiction_count": row["contradiction_count"],
            })

        results.sort(key=lambda x: x["belief"], reverse=True)
        return results[:limit]

    @staticmethod
    def get_confidence_label(belief: float, variance: float) -> str:
        confidence = 1.0 - variance
        if belief > 0.9 and confidence > 0.8:
            return "very confident"
        if belief > 0.7 and confidence > 0.6:
            return "confident"
        if belief > 0.5 and confidence > 0.4:
            return "somewhat sure"
        if belief > 0.3:
            return "vaguely remember"
        return "not sure"

    # ── Batch decay for background maintenance ───────────────────────────

    def apply_decay_batch(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM facts WHERE is_active = 1")
        for row in cursor.fetchall():
            try:
                self.apply_temporal_decay(row[0])
            except Exception:
                logger.exception("apply_decay_batch: decay failed for fact %s", row[0])
