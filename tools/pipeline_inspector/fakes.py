"""In-memory fakes for every external dependency of the message pipeline.

The real stage classes run unchanged; only the *infrastructure* they were
injected with is swapped. Each fake implements the exact surface the stage
touches (verified against current source):

- LLMCallStage        -> ``await generator(current_messages=, context=, tone_modifier=)``
- ResponseDecisionStage -> ``affect_engine.snapshot_cached(user_id)`` (+.valence/.familiarity)
- MemoryRetrievalStage -> ``memory.get_user_profile(user_id)``, ``retrieval.build_context(...)``
- PromptAssemblyStage  -> ``memory.belief_engine.get_facts_for_user`` / ``memory.get_relevant_beliefs``
- MemoryWriteStage     -> ``memory.add_memory_enhanced(**kw)``, ``update_relationship``,
                           ``log_activity``, ``affect_engine.record_sentiment``
- ResponseCleaningStage -> ``thinking_filter.filter(raw)``
- PersonalityStage      -> ``mood_state.get_tone_modifier(user_id)`` / ``personality.get_*``
"""
from __future__ import annotations

from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
    MessagePipeline,
)
from tools.pipeline_inspector.scenario import Scenario, _Snap

DEFAULT_LLM_RESPONSE = "lol yeah that tracks honestly"


class CannedLLM:
    """Scripted async generator — replaces the real llama connector.

    Faithfully records the system prompt it would forward to the model (via the
    SAME ``resolve_system_prompt`` the real ``get_response_natural`` uses), so
    the ``planner_constraints_survive`` check can assert against what is
    ACTUALLY sent — not an intermediate ``ctx.system_prompt`` field that a
    downstream rebuild may discard.
    """

    def __init__(self, response: str = DEFAULT_LLM_RESPONSE) -> None:
        self.response = response
        self.last_payload_system: str = ""

    async def __call__(
        self,
        *,
        current_messages: list[dict[str, Any]] | None = None,
        context: str = "",
        tone_modifier: str = "",
    ) -> str:
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
            resolve_system_prompt,
        )
        self.last_payload_system = resolve_system_prompt(
            current_messages=current_messages or [],
            tone_modifier=tone_modifier,
        )
        return self.response


class FakeAffectEngine:
    """Per-user affect snapshots + a sentiment recorder."""

    def __init__(self) -> None:
        self._snapshots: dict[str, _Snap] = {}
        self.sentiments: list[tuple[str, float]] = []

    def set_snapshot(self, user_id: str, snap: _Snap) -> None:
        self._snapshots[str(user_id)] = snap

    def snapshot_cached(self, user_id: str | None) -> _Snap | None:
        return self._snapshots.get(str(user_id))

    async def record_sentiment(self, user_id: str, compound: float) -> None:
        self.sentiments.append((str(user_id), compound))


class FakeBeliefEngine:
    """Bayesian-ish facts surface for PromptAssembly's ``_facts_context``."""

    def __init__(self) -> None:
        self.facts: list[dict[str, Any]] = []
        self.stored: list[dict[str, Any]] = []

    def set_facts(self, facts: list[dict[str, Any]]) -> None:
        self.facts = facts

    def get_facts_for_user(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.facts[:limit]

    @staticmethod
    def get_confidence_label(belief: float, variance: float) -> str:
        if belief >= 0.7:
            return "high confidence"
        if belief >= 0.4:
            return "medium confidence"
        return "low confidence"

    def store_fact(self, **kwargs: Any) -> None:
        self.stored.append(kwargs)

    def observe(self, *args: Any, **kwargs: Any) -> None:
        return None


class FakeMemorySystem:
    """Dict-backed stand-in for QdrantMemorySystem + belief engine."""

    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []
        self._profiles: dict[str, dict[str, Any]] = {}
        self._beliefs: list[dict[str, Any]] = []
        self.belief_engine: FakeBeliefEngine | None = None

    def set_user_profile(self, user_id: str, profile: dict[str, Any]) -> None:
        self._profiles[str(user_id)] = profile

    def set_beliefs(self, beliefs: list[dict[str, Any]]) -> None:
        self._beliefs = beliefs

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        return self._profiles.get(str(user_id), {})

    def get_relevant_beliefs(self, query: str = "", limit: int = 5) -> list[dict[str, Any]]:
        return self._beliefs[:limit]

    def add_memory_enhanced(self, **kwargs: Any) -> None:
        self.writes.append(kwargs)

    def update_relationship(self, *args: Any, **kwargs: Any) -> None:
        return None

    def log_activity(self, *args: Any, **kwargs: Any) -> None:
        return None


class FakeRetrieval:
    """Returns the scenario's seeded retrieval recipe."""

    def __init__(self, scenario: Scenario) -> None:
        self._scenario = scenario

    def build_context(
        self,
        user_messages: list[dict[str, Any]] | None = None,
        channel_id: str = "",
        mood_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        s = self._scenario
        return {
            "facts": s.facts,
            "beliefs": s.beliefs,
            "evidence_memories": [],
            "episode_memories": [],
            "utterance_memories": [],
            "recent_conversation": s.recent_messages,
            "relationships": [],
        }


class FakeMentionTranslator:
    def update_cache(self, *args: Any, **kwargs: Any) -> None:
        return None

    def clean_for_bot(self, content: str, message: Any = None) -> str:
        return content

    def clean_bot_self_mention(self, content: str) -> str:
        return content


class FakeTemporal:
    """No ``resolve_dates`` — TemporalStage hasattr-guards to a no-op."""


class FakePersonality:
    def get_personality_context(self) -> str:
        return "You enjoy talking about games, code, and indie music."

    def get_tone_modifier(self) -> str:
        return "casual"

    def update_from_conversation(self, **kwargs: Any) -> None:
        return None


class FakeMoodState:
    def __init__(self, tone: str = "") -> None:
        self._tone = tone

    def get_tone_modifier(self, user_id: str) -> str:
        return self._tone

    def update_from_conversation(self, **kwargs: Any) -> None:
        # MemoryWriteStage is wired `personality=mood_state` by MessagePipeline.build,
        # so this mutator must exist here. No-op for dry-run tone control.
        return None


class FakeThinkingFilter:
    def filter(self, raw: str) -> str:
        return raw


def _make_affect(scenario: Scenario) -> FakeAffectEngine:
    engine = FakeAffectEngine()
    if scenario.affect is not None:
        engine.set_snapshot(scenario.user_id, scenario.affect)
    return engine


def _make_memory(scenario: Scenario) -> FakeMemorySystem:
    memory = FakeMemorySystem()
    if scenario.user_profile:
        memory.set_user_profile(scenario.user_id, scenario.user_profile)
    if scenario.facts:
        engine = FakeBeliefEngine()
        engine.set_facts(scenario.facts)
        memory.belief_engine = engine
    if scenario.beliefs:
        memory.set_beliefs(scenario.beliefs)
    return memory


def build_pipeline(
    mode: str = "dry",
    scenario: Scenario | None = None,
    response: str = DEFAULT_LLM_RESPONSE,
    force_reply: bool = False,
    **overrides: Any,
) -> MessagePipeline:
    """Assemble the REAL MessagePipeline with fakes injected.

    ``mode="dry"`` fakes every external dependency (zero running infra).
    ``mode="real"`` accepts already-constructed real stores via ``overrides``
    (memory_system, retrieval, affect_engine, mood_state, ...); the LLM stays
    canned unless ``response_generator`` is overridden.

    ``force_reply=True`` puts the scenario's author in ``creator_ids``, so the
    real ResponseDecisionStage's creator hard-override replies deterministically
    (the boltzmann engine otherwise may ``boltzmann_ignore`` and halt the flow).

    Note: force_reply does NOT bypass ResponseDecisionStage's logic. The stage
    still advances the dynamics engine's physics state (``observe_message`` +
    ``allocate_attention``), computes full salience (including the affect
    snapshot's familiarity bonus), and reads user valence/familiarity — only
    the final ``dynamics.decide_action(...)`` Boltzmann sampling is skipped in
    favor of the production creator override. To observe the real Boltzmann
    decision on non-creator input, build with ``force_reply=False`` and inspect
    ``ctx.halt_reason`` / ``ctx.should_respond``.
    """
    scenario = scenario or Scenario(content="hello")
    llm = overrides.pop("response_generator", None) or CannedLLM(response)
    affect = overrides.pop("affect_engine", None) or _make_affect(scenario)
    memory = overrides.pop("memory_system", None) or _make_memory(scenario)
    retrieval = overrides.pop("retrieval", None) or FakeRetrieval(scenario)
    creator_ids = overrides.pop("creator_ids", None)
    if force_reply:
        creator_ids = frozenset(creator_ids or ()) | {scenario.user_id}

    return MessagePipeline.build(
        memory_system=memory,
        retrieval=retrieval,
        personality=overrides.pop("personality", None) or FakePersonality(),
        temporal_context=overrides.pop("temporal_context", None) or FakeTemporal(),
        response_generator=llm,
        thinking_filter=overrides.pop("thinking_filter", None) or FakeThinkingFilter(),
        mention_translator=overrides.pop("mention_translator", None) or FakeMentionTranslator(),
        mood_state=overrides.pop("mood_state", None) or FakeMoodState(),
        client=overrides.pop("client", None),
        small_llm=overrides.pop("small_llm", None),
        dynamics_engine=overrides.pop("dynamics_engine", None),
        creator_ids=creator_ids,
        affect_engine=affect,
        **overrides,
    )


__all__ = [
    "CannedLLM",
    "FakeAffectEngine",
    "FakeBeliefEngine",
    "FakeMemorySystem",
    "FakeRetrieval",
    "FakeMentionTranslator",
    "FakeTemporal",
    "FakePersonality",
    "FakeMoodState",
    "FakeThinkingFilter",
    "build_pipeline",
]
