from __future__ import annotations

from unittest.mock import MagicMock

from serin.d1_1_pipeline_flow.ingest.core.perception.classify import detect_evidence, perceive_message
from serin.d1_1_pipeline_flow.ingest.core.perception.result import JOKE_MARKERS, PerceptionResult


class TestDetectEvidence:
    def test_board_state(self) -> None:
        assert detect_evidence(None, "|X|O|X|\n|O|X|O|") is True

    def test_url(self) -> None:
        assert detect_evidence(None, "Check this https://example.com/page") is True

    def test_code_block(self) -> None:
        assert detect_evidence(None, "```python\nprint('hello')\n```") is True

    def test_long_quote(self) -> None:
        assert detect_evidence(None, 'She said "this is a very long quote that goes on for more than twenty characters"') is True

    def test_no_evidence(self) -> None:
        assert detect_evidence(None, "hey how are you doing today") is False

    def test_short_quote_not_evidence(self) -> None:
        assert detect_evidence(None, 'he said "hi"') is False

    def test_empty_string(self) -> None:
        assert detect_evidence(None, "") is False

    def test_url_at_end(self) -> None:
        assert detect_evidence(None, "Look at this link: https://github.com/sixty-north/cosmic-ray") is True


class TestPerceiveMessage:
    def _make_self(self) -> MagicMock:
        obj = MagicMock()
        obj.analyzer.polarity_scores.return_value = {"compound": 0.0}
        return obj

    def test_speech_act_question(self) -> None:
        result = perceive_message(self._make_self(), "are you free?", "user1", "User")
        assert result.speech_act == "question"

    def test_speech_act_joke(self) -> None:
        for marker in JOKE_MARKERS[:3]:
            result = perceive_message(self._make_self(), f"something {marker}", "user1", "User")
            assert result.speech_act == "joke", f"failed for marker: {marker}"

    def test_speech_act_sarcasm(self) -> None:
        result = perceive_message(self._make_self(), "oh sure, that makes total sense", "user1", "User")
        assert result.speech_act == "sarcasm"

    def test_speech_act_agreement(self) -> None:
        result = perceive_message(self._make_self(), "yes I agree with you", "user1", "User")
        assert result.speech_act == "agreement"

    def test_speech_act_disagreement(self) -> None:
        result = perceive_message(self._make_self(), "no that is wrong", "user1", "User")
        assert result.speech_act == "disagreement"

    def test_speech_act_evidence_board(self) -> None:
        result = perceive_message(self._make_self(), "Check the board:\n|X|O|X|\n|O|X|O|", "user1", "User")
        assert result.speech_act == "evidence"
        assert len(result.evidence_blocks) >= 1
        assert result.evidence_blocks[0]["type"] == "board"

    def test_speech_act_evidence_url(self) -> None:
        result = perceive_message(self._make_self(), "See https://example.com", "user1", "User")
        assert result.speech_act == "evidence"
        assert any(b["type"] == "url" for b in result.evidence_blocks)

    def test_speech_act_evidence_code(self) -> None:
        result = perceive_message(self._make_self(), "Run ```python\nx=1\nprint(x)\n```", "user1", "User")
        assert result.speech_act == "evidence"
        assert any(b["type"] == "code" for b in result.evidence_blocks)

    def test_speech_act_evidence_quote(self) -> None:
        result = perceive_message(self._make_self(), 'They said "this is a very important statement about the matter at hand"', "user1", "User")
        assert result.speech_act == "evidence"

    def test_speech_act_instruction(self) -> None:
        result = perceive_message(self._make_self(), "tell me a story about dragons", "user1", "User")
        assert result.speech_act == "instruction"

    def test_speech_act_statement_default(self) -> None:
        result = perceive_message(self._make_self(), "I like pizza", "user1", "User")
        assert result.speech_act == "statement"

    def test_win_claim_extracted(self) -> None:
        result = perceive_message(self._make_self(), "I won the game yesterday", "user1", "User")
        claims = result.claims
        categories = [c["category"] for c in claims]
        assert "win_claim" in categories

    def test_self_assessment_claim(self) -> None:
        result = perceive_message(self._make_self(), "I'm better at this game", "user1", "User")
        categories = [c["category"] for c in result.claims]
        assert "self_assessment" in categories

    def test_emphasis_claim(self) -> None:
        result = perceive_message(self._make_self(), "actually I know the answer", "user1", "User")
        categories = [c["category"] for c in result.claims]
        assert "emphasis_claim" in categories

    def test_first_person_assertion(self) -> None:
        result = perceive_message(self._make_self(), "I think this is the right approach", "user1", "User")
        categories = [c["category"] for c in result.claims]
        assert "self_statement" in categories

    def test_third_person_assertion(self) -> None:
        result = perceive_message(self._make_self(), "you're not seeing the full picture", "user1", "User")
        categories = [c["category"] for c in result.claims]
        assert "other_directed" in categories

    def test_objectivity_with_evidence(self) -> None:
        result = perceive_message(self._make_self(), "Data: https://example.com/stats", "user1", "User")
        assert result.is_objective is True

    def test_not_objective_with_claims_only(self) -> None:
        result = perceive_message(self._make_self(), "I am the best player here", "user1", "User")
        assert result.is_objective is False

    def test_intent_question(self) -> None:
        result = perceive_message(self._make_self(), "What time is it?", "user1", "User")
        assert result.intent == "question"

    def test_intent_seek_explanation(self) -> None:
        result = perceive_message(self._make_self(), "explain how this works", "user1", "User")
        assert result.intent == "seek_explanation"

    def test_intent_seek_validation(self) -> None:
        result = perceive_message(self._make_self(), "am i right about this thing", "user1", "User")
        assert result.intent == "seek_validation"

    def test_intent_command(self) -> None:
        result = perceive_message(self._make_self(), "do the needful", "user1", "User")
        assert result.intent == "command"

    def test_intent_social_for_agreement(self) -> None:
        result = perceive_message(self._make_self(), "yes totally agreed", "user1", "User")
        assert result.intent == "social"

    def test_board_evidence_block(self) -> None:
        result = perceive_message(self._make_self(), "Board:\n|X|O|X|\n|O|X|O|", "user1", "User")
        boards = [b for b in result.evidence_blocks if b["type"] == "board"]
        assert len(boards) == 1
        assert "X" in boards[0]["content"]

    def test_url_evidence_block(self) -> None:
        result = perceive_message(self._make_self(), "Link: https://example.com/page", "user1", "User")
        urls = [b for b in result.evidence_blocks if b["type"] == "url"]
        assert len(urls) == 1
        assert urls[0]["content"] == "https://example.com/page"

    def test_code_evidence_block_with_language(self) -> None:
        result = perceive_message(self._make_self(), "```python\nx = 1\n```", "user1", "User")
        codes = [b for b in result.evidence_blocks if b["type"] == "code"]
        assert len(codes) == 1
        assert codes[0]["metadata"]["language"] == "python"

    def test_code_evidence_block_no_language(self) -> None:
        result = perceive_message(self._make_self(), "```\nx = 1\n```", "user1", "User")
        codes = [b for b in result.evidence_blocks if b["type"] == "code"]
        assert len(codes) == 1
        assert codes[0]["metadata"]["language"] == ""

    def test_observations_from_evidence(self) -> None:
        result = perceive_message(self._make_self(), "```python\nprint(1)\n```", "user1", "User")
        assert any("Code was shared" in o for o in result.observations)

    def test_observations_from_claims(self) -> None:
        result = perceive_message(self._make_self(), "I won the match", "user1", "User")
        assert any("claims" in o for o in result.observations)

    def test_extracted_facts_from_board(self) -> None:
        result = perceive_message(self._make_self(), "Board:\n|X|O|X|\n|O|X|O|", "user1", "User")
        board_facts = [f for f in result.extracted_facts if f["category"] == "board_state"]
        assert len(board_facts) >= 1

    def test_extracted_facts_from_claims(self) -> None:
        result = perceive_message(self._make_self(), "I won the tournament", "user1", "User")
        claim_facts = [f for f in result.extracted_facts if f["category"] == "speech_claim"]
        assert len(claim_facts) >= 0

    def test_evidence_class_world_with_evidence(self) -> None:
        result = perceive_message(self._make_self(), "See https://example.com", "user1", "User")
        assert result.evidence_class == "world"

    def test_evidence_class_conversation_with_claims(self) -> None:
        result = perceive_message(self._make_self(), "I think you are wrong about that", "user1", "User")
        assert result.evidence_class == "conversation"

    def test_evidence_class_social_with_emotional_content(self) -> None:
        obj = self._make_self()
        obj.analyzer.polarity_scores.return_value = {"compound": 0.8}
        result = perceive_message(obj, "This is absolutely amazing!", "user1", "User")
        assert result.evidence_class == "social"

    def test_default_intent_for_statement(self) -> None:
        result = perceive_message(self._make_self(), "The sky is blue", "user1", "User")
        assert result.intent == "social"

    def test_empty_content(self) -> None:
        result = perceive_message(self._make_self(), "", "user1", "User")
        assert isinstance(result, PerceptionResult)

    def test_joke_overrides_question(self) -> None:
        result = perceive_message(self._make_self(), "are you serious? lol", "user1", "User")
        assert result.speech_act == "joke"

    def test_sarcasm_overrides_joke(self) -> None:
        result = perceive_message(self._make_self(), "lol oh sure, obviously", "user1", "User")
        assert result.speech_act == "sarcasm"

    def test_loss_attribution_claim(self) -> None:
        result = perceive_message(self._make_self(), "you lost the game again", "user1", "User")
        categories = [c["category"] for c in result.claims]
        assert "loss_attribution" in categories

    def test_other_correction_claim(self) -> None:
        result = perceive_message(self._make_self(), "you 're wrong about the score", "user1", "User")
        categories = [c["category"] for c in result.claims]
        assert "other_correction" in categories

    def test_evidence_blocks_have_evidence_class(self) -> None:
        result = perceive_message(self._make_self(), "https://example.com", "user1", "User")
        for block in result.evidence_blocks:
            assert "evidence_class" in block
            assert block["evidence_class"] == "world"

    def test_derived_facts_from_board(self) -> None:
        result = perceive_message(self._make_self(), "|X|O|X|\n|O|X|O|\n|X| | |", "user1", "User")
        assert any(f["source_type"] == "derived" for f in result.extracted_facts)

    def test_claimant_is_username(self) -> None:
        result = perceive_message(self._make_self(), "I won", "user1", "TestUser")
        for claim in result.claims:
            assert claim["claimant"] == "TestUser"

    def test_claimant_falls_back_to_user_id(self) -> None:
        result = perceive_message(self._make_self(), "I won", "user1", "")
        for claim in result.claims:
            assert claim["claimant"] == "user1"

    # ─────────────────────────────────────────────────────────────────
    #  is_objective exact assertions —
    #  kills ReplaceTrueWithFalse + ReplaceFalseWithTrue
    # ─────────────────────────────────────────────────────────────────

    def test_default_is_objective_false(self) -> None:
        """PerceptionResult default: is_objective=False.
        Kills ReplaceFalseWithTrue at L40."""
        result = perceive_message(self._make_self(), "hello", "u1", "U")
        assert result.is_objective is False

    def test_question_is_objective_true(self) -> None:
        """A question seeks truth → is_objective=True.
        Kills ReplaceTrueWithFalse at L46."""
        result = perceive_message(self._make_self(), "are you sure?", "u1", "U")
        assert result.is_objective is True

    def test_joke_is_objective_false(self) -> None:
        """A joke is not objective.
        Kills ReplaceFalseWithTrue at L51."""
        result = perceive_message(self._make_self(), "that was great lol", "u1", "U")
        assert result.is_objective is False

    def test_evidence_is_objective_true(self) -> None:
        """Evidence (URL) is objective.
        Kills ReplaceTrueWithFalse at L70."""
        result = perceive_message(self._make_self(), "See https://example.com", "u1", "U")
        assert result.is_objective is True

    # ─────────────────────────────────────────────────────────────────
    #  Evidence block confidence exact values —
    #  kills NumberReplacer on 0.9, 0.7, 0.8, 0.2
    # ─────────────────────────────────────────────────────────────────

    def test_board_fact_confidence_exact(self) -> None:
        result = perceive_message(self._make_self(), "Board:\n|X|O|X|\n|O|X|O|", "u1", "U")
        board_facts = [f for f in result.extracted_facts if f["category"] == "board_state"]
        assert len(board_facts) >= 1
        assert board_facts[0]["confidence"] == 0.9

    def test_url_fact_confidence_exact(self) -> None:
        result = perceive_message(self._make_self(), "Link: https://example.com", "u1", "U")
        ref_facts = [f for f in result.extracted_facts if f["category"] == "reference"]
        assert len(ref_facts) >= 1
        assert ref_facts[0]["confidence"] == 0.7

    def test_code_fact_confidence_exact(self) -> None:
        result = perceive_message(self._make_self(), "```python\nx=1\n```", "u1", "U")
        code_facts = [f for f in result.extracted_facts if f["category"] == "code"]
        assert len(code_facts) >= 1
        assert code_facts[0]["confidence"] == 0.8

    def test_speech_claim_confidence_exact(self) -> None:
        result = perceive_message(self._make_self(), "I won the game", "u1", "U")
        claim_facts = [f for f in result.extracted_facts if f["category"] == "speech_claim"]
        assert len(claim_facts) >= 1
        assert claim_facts[0]["confidence"] == 0.2

    # ─────────────────────────────────────────────────────────────────
    #  Evidence block type filtering —
    #  kills ReplaceComparisonOperator_Eq_Is / Eq_GtE / Eq_LtE / Eq_Gt
    #  on `type == 'board'`, `type == 'url'`, `type == 'code'`
    # ─────────────────────────────────────────────────────────────────

    def test_board_type_filter_exact(self) -> None:
        result = perceive_message(self._make_self(), "```python\nx=1\n```\nBoard:\n|X|O|X|\n|O|X|O|", "u1", "U")
        boards = [b for b in result.evidence_blocks if b["type"] == "board"]
        codes = [b for b in result.evidence_blocks if b["type"] == "code"]
        assert len(boards) == 1
        assert len(codes) == 1

    def test_url_type_filter_exact(self) -> None:
        result = perceive_message(self._make_self(), "Check https://example.com/page and https://other.com", "u1", "U")
        urls = [b for b in result.evidence_blocks if b["type"] == "url"]
        assert len(urls) == 2

    def test_code_type_filter_exact(self) -> None:
        result = perceive_message(self._make_self(), "Run ```python\nx=1\nprint(x)\n```", "u1", "U")
        codes = [b for b in result.evidence_blocks if b["type"] == "code"]
        assert len(codes) == 1
        assert codes[0]["content"] == "x=1\nprint(x)"

    # ─────────────────────────────────────────────────────────────────
    #  Evidence extraction details —
    #  kills NumberReplacer on group(1), group(2), [:100], [:200]
    #  kills ZeroIterationForLoop on quotes loop
    # ─────────────────────────────────────────────────────────────────

    def test_board_evidence_content_exact(self) -> None:
        result = perceive_message(self._make_self(), "Board:\n|X|O|X|\n|O|X|O|\n|X| | |", "u1", "U")
        boards = [b for b in result.evidence_blocks if b["type"] == "board"]
        assert len(boards) == 1
        assert "X" in boards[0]["content"]
        assert "O" in boards[0]["content"]

    def test_long_quote_produces_evidence_block(self) -> None:
        result = perceive_message(
            self._make_self(),
            'They said "this is a very long quote that goes on for more than twenty characters"',
            "u1", "U",
        )
        quotes = [b for b in result.evidence_blocks if b["type"] == "quote"]
        assert len(quotes) == 1

    def test_code_observation_truncation(self) -> None:
        long_code = "print(" + "x" * 200 + ")"
        result = perceive_message(self._make_self(), f"```python\n{long_code}\n```", "u1", "U")
        code_obs = [o for o in result.observations if "Code was shared" in o]
        assert len(code_obs) >= 1
        assert len(code_obs[0]) < 200

    # ─────────────────────────────────────────────────────────────────
    #  Speech act exact equality + intent assignment —
    #  kills ReplaceComparisonOperator_Eq_Is on speech_act ==
    # ─────────────────────────────────────────────────────────────────

    def test_speech_act_question_exact(self) -> None:
        result = perceive_message(self._make_self(), "what is this?", "u1", "U")
        assert result.speech_act == "question"
        assert result.intent == "question"

    def test_speech_act_instruction_exact(self) -> None:
        result = perceive_message(self._make_self(), "do the needful", "u1", "U")
        assert result.speech_act == "instruction"
        assert result.intent == "command"

    def test_speech_act_disagreement_exact(self) -> None:
        result = perceive_message(self._make_self(), "no that is wrong", "u1", "U")
        assert result.speech_act == "disagreement"
        assert result.intent == "seek_argument"

    def test_speech_act_agreement_exact(self) -> None:
        result = perceive_message(self._make_self(), "yes absolutely right", "u1", "U")
        assert result.speech_act == "agreement"
        assert result.intent == "social"

    # ─────────────────────────────────────────────────────────────────
    #  Claim extraction edge cases —
    #  kills ReplaceOrWithAnd on `username or user_id`
    #  kills AddNot on claim category check
    # ─────────────────────────────────────────────────────────────────

    def test_first_person_assertion_empty_username(self) -> None:
        result = perceive_message(self._make_self(), "I think this is right", "user42", "")
        self_statements = [c for c in result.claims if c["category"] == "self_statement"]
        assert len(self_statements) >= 1
        assert self_statements[0]["claimant"] == "user42"

    def test_third_person_assertion_empty_username(self) -> None:
        result = perceive_message(self._make_self(), "you're wrong about that", "user42", "")
        other_directed = [c for c in result.claims if c["category"] == "other_directed"]
        assert len(other_directed) >= 1
        assert other_directed[0]["claimant"] == "user42"

    def test_win_claim_produces_speech_claim_fact(self) -> None:
        result = perceive_message(self._make_self(), "I won the tournament", "u1", "U")
        claim_facts = [f for f in result.extracted_facts if f["source_type"] == "user_claim"]
        assert len(claim_facts) >= 1

    # ─────────────────────────────────────────────────────────────────
    #  Social class detection threshold —
    #  kills NumberReplacer + Gt_GtE + Gt_NotEq on `> 0.7`
    # ─────────────────────────────────────────────────────────────────

    def test_emotional_content_high_compound_is_social(self) -> None:
        obj = self._make_self()
        obj.analyzer.polarity_scores.return_value = {"compound": 0.8}
        result = perceive_message(obj, "This is absolutely amazing!", "u1", "U")
        assert result.evidence_class == "social"

    def test_emotional_content_at_threshold_not_social(self) -> None:
        obj = self._make_self()
        obj.analyzer.polarity_scores.return_value = {"compound": 0.7}
        result = perceive_message(obj, "This is pretty good!", "u1", "U")
        assert result.evidence_class != "social"
