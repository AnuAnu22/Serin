"""Tests for per-relationship personality state / emotional persistence.

Covers the three behaviors the design requires (CODING_GUIDELINES §4):
  1. Two users in different relationships get different tone modifiers.
  2. A mood set with user A does not bleed into a fresh interaction with B.
  3. A mood with user A persists (and accumulates) across multiple A messages.
"""
from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
    PersonalityState,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
    relationship_category,
)


class TestRelationshipCategory:
    """valence/familiarity → stranger/enemy/friend/acquaintance mapping."""

    def test_stranger_is_low_familiarity(self) -> None:
        assert relationship_category(0.0, 0.05) == "stranger"

    def test_enemy_is_negative_valence(self) -> None:
        assert relationship_category(-0.5, 0.6) == "enemy"

    def test_enemy_wins_over_friend_on_bad_valence(self) -> None:
        assert relationship_category(-0.5, 0.8) == "enemy"

    def test_friend_requires_familiarity_and_positivity(self) -> None:
        assert relationship_category(0.6, 0.7) == "friend"

    def test_acquaintance_is_in_between(self) -> None:
        assert relationship_category(0.2, 0.3) == "acquaintance"


class TestPerUserToneModifier:
    def test_two_users_different_relationships_get_different_tone(self) -> None:
        state = PersonalityState()
        state.update_from_conversation('energetic', [], 12, user_id='A', relationship='enemy')
        state.update_from_conversation('chill', [], 12, user_id='B', relationship='friend')
        assert state.get_tone_modifier('A') != state.get_tone_modifier('B')

    def test_fresh_user_gets_global_default_not_another_users_mood(self) -> None:
        """User B who has never interacted must start neutral, never inheriting
        the mood set for user A."""
        state = PersonalityState()
        state.update_from_conversation('neutral', ['humorous'], 12, user_id='A', relationship='enemy')
        assert state.get_tone_modifier('B') == PersonalityState().get_tone_modifier()
        assert state.get_tone_modifier('B') != state.get_tone_modifier('A')

    def test_user_id_none_uses_global_default(self) -> None:
        """Callers that pass no user (control panel, voice gateway) keep the
        global mood, unaffected by per-user updates."""
        state = PersonalityState()
        state.update_from_conversation('energetic', [], 12, user_id='A', relationship='enemy')
        assert state.get_tone_modifier() == PersonalityState().get_tone_modifier()


class TestMoodPersistence:
    def test_mood_with_user_a_persists_across_messages(self) -> None:
        """A's sass nudges up on each message (persistence, not a single-use
        nudge) while dormant user B stays at the neutral default."""
        state = PersonalityState()
        state.update_from_conversation('neutral', ['humorous'], 12, user_id='A', relationship='enemy')
        sass_1 = state._users['A']['sass_level']
        state.update_from_conversation('neutral', ['humorous'], 12, user_id='A', relationship='enemy')
        sass_2 = state._users['A']['sass_level']
        assert sass_2 > sass_1  # accumulated, so the mood persisted
        # B, untouched, still reads as a brand-new relationship.
        assert state.get_tone_modifier('B') == PersonalityState().get_tone_modifier()
