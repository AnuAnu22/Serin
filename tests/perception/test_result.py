from __future__ import annotations

from serin.d1_1_pipeline_flow.ingest.core.perception.result import (
    ARGUMENT_KEYWORDS,
    CLAIM_PATTERNS,
    JOKE_MARKERS,
    SARCASM_MARKERS,
    PerceptionResult,
)


class TestPerceptionResult:
    def test_default_speech_act(self) -> None:
        r = PerceptionResult(speech_act="statement", is_objective=False)
        assert r.speech_act == "statement"

    def test_default_is_objective(self) -> None:
        r = PerceptionResult(speech_act="statement", is_objective=True)
        assert r.is_objective is True

    def test_default_evidence_class(self) -> None:
        r = PerceptionResult(speech_act="statement", is_objective=False)
        assert r.evidence_class == "conversation"

    def test_default_intent(self) -> None:
        r = PerceptionResult(speech_act="statement", is_objective=False)
        assert r.intent == "statement"

    def test_default_evidence_blocks_empty(self) -> None:
        r = PerceptionResult(speech_act="statement", is_objective=False)
        assert r.evidence_blocks == []

    def test_default_claims_empty(self) -> None:
        r = PerceptionResult(speech_act="statement", is_objective=False)
        assert r.claims == []

    def test_default_observations_empty(self) -> None:
        r = PerceptionResult(speech_act="statement", is_objective=False)
        assert r.observations == []

    def test_default_extracted_facts_empty(self) -> None:
        r = PerceptionResult(speech_act="statement", is_objective=False)
        assert r.extracted_facts == []

    def test_custom_evidence_class(self) -> None:
        r = PerceptionResult(speech_act="evidence", is_objective=True, evidence_class="world")
        assert r.evidence_class == "world"

    def test_custom_intent(self) -> None:
        r = PerceptionResult(speech_act="question", is_objective=True, intent="question")
        assert r.intent == "question"

    def test_with_evidence_blocks(self) -> None:
        blocks = [{"type": "url", "content": "https://example.com", "evidence_class": "world", "metadata": {}}]
        r = PerceptionResult(speech_act="evidence", is_objective=True, evidence_blocks=blocks)
        assert len(r.evidence_blocks) == 1
        assert r.evidence_blocks[0]["type"] == "url"

    def test_with_claims(self) -> None:
        claims = [{"claimant": "user1", "content": "I won", "category": "win_claim"}]
        r = PerceptionResult(speech_act="statement", is_objective=False, claims=claims)
        assert len(r.claims) == 1
        assert r.claims[0]["category"] == "win_claim"

    def test_with_observations(self) -> None:
        obs = ["Derived: X has 4 in a row"]
        r = PerceptionResult(speech_act="evidence", is_objective=True, observations=obs)
        assert len(r.observations) == 1

    def test_with_extracted_facts(self) -> None:
        facts = [{"content": "test", "category": "board_state", "confidence": 0.9, "source_type": "derived"}]
        r = PerceptionResult(speech_act="evidence", is_objective=True, extracted_facts=facts)
        assert len(r.extracted_facts) == 1


class TestPatterns:
    def test_claim_patterns_not_empty(self) -> None:
        assert len(CLAIM_PATTERNS) > 0

    def test_sarcasm_markers_not_empty(self) -> None:
        assert len(SARCASM_MARKERS) > 0

    def test_joke_markers_not_empty(self) -> None:
        assert len(JOKE_MARKERS) > 0

    def test_argument_keywords_not_empty(self) -> None:
        assert len(ARGUMENT_KEYWORDS) > 0

    def test_claim_patterns_are_tuples(self) -> None:
        for pattern in CLAIM_PATTERNS:
            assert isinstance(pattern, tuple)
            assert len(pattern) == 2

    def test_win_claim_pattern(self) -> None:
        import re
        assert re.search(CLAIM_PATTERNS[0][0], "I won") is not None

    def test_loss_attribution_pattern(self) -> None:
        import re
        assert re.search(CLAIM_PATTERNS[1][0], "you lost") is not None
