"""
ConversationDynamicsEngine
---------------------------
Continuous physics simulation of Serin's conversational state.

Replaces the 12 boolean rules in ResponseController.should_respond()
(rules 4-12) with mathematical models:

1. Markowitz Portfolio Theory — global attention allocation
2. Kuramoto Oscillator — per-channel momentum/flow
3. KL Divergence — topic shift detection
4. Boltzmann Distribution — action selection (reply/react/ignore)
5. Hawkes Process — response timing/latency

Rules 1-3 from ResponseController are HARD OVERRIDES:
- Creator (Rin) → always respond
- Discord @mention → always respond
- Bot name in message → always respond
These are checked BEFORE the engine is consulted.
"""
# --- Imports ---
from __future__ import annotations

import logging
import math
import secrets
import time
from collections import defaultdict
from typing import Any

logger = logging.getLogger("serin")

# --- Types ---
# (none)

# --- Constants ---
# (none)

# --- Entry ---
class ConversationDynamicsEngine:
    """Continuous physics simulation of Serin's conversational state."""

    def __init__(self) -> None:
        self.channels: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "momentum": 0.0,
            "phase": 0.0,
            "frequency": 0.0,
            "last_active": 0.0,
            "message_times": [],
            "word_counts": defaultdict(int),
            "total_words": 0,
            "temperature": 1.0,
            "participants": set(),
            "last_action": "none",
            "last_action_time": 0.0,
        })
        self.attention_allocation: dict[str, float] = {}
        self._last_allocation_time = 0.0

    # --------------------------------------------------------
    # CORE UPDATE — called for EVERY message Serin sees
    # --------------------------------------------------------
    def observe_message(self, channel_id: str, content: str,
                        user_id: str, timestamp: float | None = None) -> None:
        """Update channel physics state. Call for every incoming message."""
        ts = timestamp or time.time()
        ch = self.channels[channel_id]
        dt = ts - ch["last_active"] if ch["last_active"] > 0 else 60.0
        ch["last_active"] = ts
        ch["participants"].add(user_id)
        ch["message_times"].append(ts)
        ch["message_times"] = ch["message_times"][-50:]

        if dt > 0:
            instant_freq = 1.0 / dt
            ch["frequency"] = 0.8 * ch["frequency"] + 0.2 * instant_freq

        omega = ch["frequency"]
        forcing = 1.0 if dt < 5.0 else 0.0
        ch["phase"] = (ch["phase"] + omega * dt + forcing * 0.5) % (2 * math.pi)

        # ── Highly responsive momentum calculation ──────────────────────
        # Direct boost on ANY message arrival
        boost = 0.35

        # Extra boost for quick back-and-forth (dt < 10 seconds)
        if dt > 0 and dt < 10.0:
            boost = 0.55
        elif dt == 0:  # First message or very rapid burst
            boost = 0.50

        ch["momentum"] = min(1.0, ch["momentum"] + boost)

        # Decay ONLY applies after a period of silence (> 20 seconds)
        # This keeps momentum high during an active conversation
        if dt > 20.0:
            decay = (dt - 20.0) * 0.015
            ch["momentum"] = max(0.0, ch["momentum"] - decay)

        words = [w for w in content.lower().split() if len(w) > 2]
        if words and ch["total_words"] > 10:
            epsilon = 1.0
            vocab = set(ch["word_counts"].keys()) | set(words)

            old_counts = {w: ch["word_counts"].get(w, 0) for w in vocab}
            total_old = sum(old_counts.values()) + epsilon * len(vocab)
            p_dist = {w: (old_counts[w] + epsilon) / total_old for w in vocab}

            for w in words:
                ch["word_counts"][w] += 1
                ch["total_words"] += 1

            new_counts = {w: ch["word_counts"].get(w, 0) for w in vocab}
            total_new = sum(new_counts.values()) + epsilon * len(vocab)
            q_dist = {w: (new_counts[w] + epsilon) / total_new for w in vocab}

            kl_div = 0.0
            for w in vocab:
                p = p_dist[w]
                q = q_dist[w]
                if p > 0 and q > 0:
                    kl_div += p * math.log(p / q)
            if kl_div > 1.5:
                ch["momentum"] *= 0.2
                logger.debug("Topic shift in %s (KL=%.2f), momentum shattered",
                             channel_id[:8], kl_div)
        else:
            for w in words:
                ch["word_counts"][w] += 1
                ch["total_words"] += 1

        emoji_count = sum(1 for c in content if ord(c) > 0x2600)
        velocity = min(1.0, 10.0 / max(dt, 0.5))
        ch["temperature"] = 0.8 * ch["temperature"] + 0.2 * (velocity + emoji_count * 0.1)
        ch["temperature"] = max(0.5, min(5.0, ch["temperature"]))

    # --- Core ---

    # --------------------------------------------------------
    # MARKOWITZ — global attention allocation
    # --------------------------------------------------------
    def allocate_attention(self) -> None:
        """Allocate 1.0 total attention across active channels (Markowitz mean-variance)."""
        now = time.time()
        if now - self._last_allocation_time < 5.0:
            return
        self._last_allocation_time = now

        active = {
            cid: ch for cid, ch in self.channels.items()
            if now - ch["last_active"] < 300
        }
        if not active:
            self.attention_allocation.clear()
            return

        n = len(active)
        channel_ids = list(active.keys())
        lam = 0.5

        mu = {cid: ch["momentum"] * (1.0 + ch["temperature"] * 0.3)
              for cid, ch in active.items()}

        sigma: dict[str, dict[str, float]] = {}
        for i, cid_i in enumerate(channel_ids):
            sigma[cid_i] = {}
            ch = active[cid_i]
            recent_times = ch["message_times"][-10:]

            if len(recent_times) >= 2:
                intervals = [recent_times[k + 1] - recent_times[k]
                             for k in range(len(recent_times) - 1)]
                mean_int = sum(intervals) / len(intervals)
                var_int = sum((x - mean_int) ** 2 for x in intervals) / len(intervals)
                sigma[cid_i][cid_i] = var_int / max(0.1, mean_int ** 2)
            else:
                sigma[cid_i][cid_i] = 0.5

            for j, cid_j in enumerate(channel_ids):
                if i != j:
                    freq_diff = abs(ch["frequency"] - active[cid_j]["frequency"])
                    sigma[cid_i][cid_j] = math.exp(-freq_diff * 2.0) * 0.3

        utilities: dict[str, float] = {}
        for cid in channel_ids:
            variance = sigma[cid][cid]
            avg_cov = (sum(sigma[cid][other] for other in channel_ids if other != cid)
                       / max(1, n - 1))
            risk = variance + avg_cov * 0.5
            utilities[cid] = max(0.0, mu[cid] - lam * risk)

        total_utility = sum(utilities.values())
        if total_utility > 0:
            self.attention_allocation = {cid: u / total_utility
                                         for cid, u in utilities.items()}
        else:
            self.attention_allocation = {cid: 1.0 / n for cid in channel_ids}

    # --------------------------------------------------------
    # BOLTZMANN — action selection
    # --------------------------------------------------------
    def decide_action(self, channel_id: str, salience: float,
                      is_addressed: bool = False,
                      user_valence: float = 0.0,
                      user_familiarity: float = 0.0) -> str:
        """
        Choose action via Boltzmann distribution.
        Returns: "reply", "react", or "ignore"

        user_valence in [-1, 1] and user_familiarity in [0, 1) bias the
        energies toward reply when Serin likes/knows the user. Defaults
        reproduce the pre-bias distribution exactly.
        """
        ch = self.channels[channel_id]
        attention = self.attention_allocation.get(channel_id, 0.1)
        tau = max(0.1, ch["temperature"])

        e_reply = 2.0 - (ch["momentum"] * 2.5) - (salience * 2.0) - (attention * 1.5)
        e_react = 4.0 - (salience * 3.0) - (attention * 1.0) + (ch["momentum"] * 2.0)
        e_ignore = 1.5 - (salience * 2.0) - (attention * 2.0) + (ch["momentum"] * 3.0)

        # Per-user affect bias — subtle shift based on valence + familiarity.
        # Familiarity gates all bias (strangers are unaffected).
        e_reply  -= (0.5 * user_valence + 0.3) * user_familiarity
        e_react  -= 0.2 * user_familiarity
        e_ignore += 0.4 * user_valence * user_familiarity

        if is_addressed:
            e_reply -= 3.0
            e_ignore += 2.0

        energies = {"reply": e_reply, "react": e_react, "ignore": e_ignore}

        exponents = {a: -E / tau for a, E in energies.items()}
        max_exp = max(exponents.values())
        exp_sum = sum(math.exp(e - max_exp) for e in exponents.values())

        probs = {a: math.exp(e - max_exp) / exp_sum for a, e in exponents.items()}

        r = secrets.randbelow(10000) / 10000.0
        cumulative = 0.0
        for action in ["reply", "react", "ignore"]:
            cumulative += probs[action]
            if r <= cumulative:
                ch["last_action"] = action
                ch["last_action_time"] = time.time()
                return action
        return "ignore"

    # --- Helpers ---

    # --------------------------------------------------------
    # HAWKES — timing/latency
    # --------------------------------------------------------
    def _compute_hawkes_intensity(self, channel_id: str, t: float) -> float:
        """Compute Hawkes process intensity: λ(t) = μ + Σ α e^{-β(t - t_i)}."""
        ch = self.channels[channel_id]
        attention = self.attention_allocation.get(channel_id, 0.1)

        mu = 0.1 + attention * 0.5
        alpha = 0.3 + ch["momentum"] * 0.5
        beta = 0.1

        intensity = mu
        for t_i in ch["message_times"][-20:]:
            if t_i < t:
                intensity += alpha * math.exp(-beta * (t - t_i))
        return intensity

    def sample_delay(self, channel_id: str) -> float:
        """Sample response delay from Hawkes process."""
        now = time.time()
        lam = self._compute_hawkes_intensity(channel_id, now)
        u = max(0.001, min(0.999, secrets.randbelow(10000) / 10000.0))
        delay = -math.log(u) / lam if lam > 0 else 10.0
        return max(0.3, min(30.0, delay))

    def sample_reaction_delay(self, channel_id: str) -> float:
        """Sample delay for emoji reactions from Hawkes process."""
        now = time.time()
        ch = self.channels[channel_id]
        attention = self.attention_allocation.get(channel_id, 0.1)

        mu = 0.05 + attention * 0.2
        alpha = 0.2 + ch["momentum"] * 0.3
        beta = 0.05

        intensity = mu
        for t_i in ch["message_times"][-20:]:
            if t_i < now:
                intensity += alpha * math.exp(-beta * (now - t_i))

        u = max(0.001, min(0.999, secrets.randbelow(10000) / 10000.0))
        delay = -math.log(u) / intensity if intensity > 0 else 30.0
        return max(0.5, min(120.0, delay))

    # --- Errors ---
    # (none)

    # --------------------------------------------------------
    # PANEL EXPORT
    # --------------------------------------------------------
    def get_state_for_panel(self) -> dict[str, Any]:
        now = time.time()
        return {
            "channels": {
                cid: {
                    "momentum": round(ch["momentum"], 3),
                    "temperature": round(ch["temperature"], 2),
                    "phase": round(ch["phase"], 2),
                    "frequency": round(ch["frequency"], 3),
                    "participants": len(ch["participants"]),
                    "seconds_since_active": round(now - ch["last_active"], 1),
                    "last_action": ch["last_action"],
                }
                for cid, ch in self.channels.items()
                if now - ch["last_active"] < 600
            },
            "attention_allocation": {
                cid: round(w, 3) for cid, w in self.attention_allocation.items()
            },
        }
