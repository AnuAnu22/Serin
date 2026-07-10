from __future__ import annotations

from unittest.mock import MagicMock

from serin.d1_1_pipeline_flow.ingest.core.perception.personality import analyze_personality, detect_topic, get_emotional_tone


class TestAnalyzePersonality:
    def _make_self(self) -> MagicMock:
        obj = MagicMock()
        obj.memory.update_user_traits = MagicMock()
        return obj

    def test_humorous_trait_lol(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "that was funny lol")
        assert "humorous" in traits

    def test_humorous_trait_haha(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "haha good one")
        assert "humorous" in traits

    def test_humorous_trait_lmao(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "lmao no way")
        assert "humorous" in traits

    def test_polite_trait_thanks(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "thanks for the help")
        assert "polite" in traits

    def test_polite_trait_please(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "please help me")
        assert "polite" in traits

    def test_polite_trait_sorry(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "sorry about that")
        assert "polite" in traits

    def test_verbose_trait(self) -> None:
        long_text = "a" * 201
        traits = analyze_personality(self._make_self(), "user1", long_text)
        assert "verbose" in traits

    def test_concise_trait(self) -> None:
        short_text = "hi"
        traits = analyze_personality(self._make_self(), "user1", short_text)
        assert "concise" in traits

    def test_verbose_preferred_over_concise(self) -> None:
        long_text = "b" * 201
        traits = analyze_personality(self._make_self(), "user1", long_text)
        assert "verbose" in traits
        assert "concise" not in traits

    def test_enthusiastic_trait(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "wow! amazing! great!")
        assert "enthusiastic" in traits

    def test_not_enthusiastic_with_few_exclamation_marks(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "wow! amazing")
        assert "enthusiastic" not in traits

    def test_interest_gaming(self) -> None:
        self_s = self._make_self()
        traits = analyze_personality(self_s, "user1", "I love playing games on steam")
        assert self_s.memory.update_user_traits.called
        call_args, call_kwargs = self_s.memory.update_user_traits.call_args
        assert "user1" in call_args

    def test_interest_anime(self) -> None:
        self_s = self._make_self()
        analyze_personality(self_s, "user1", "I like anime and manga")
        assert self_s.memory.update_user_traits.called

    def test_interest_music(self) -> None:
        self_s = self._make_self()
        analyze_personality(self_s, "user1", "check out this song")
        assert self_s.memory.update_user_traits.called

    def test_interest_tech(self) -> None:
        self_s = self._make_self()
        analyze_personality(self_s, "user1", "I love programming and ai")
        assert self_s.memory.update_user_traits.called

    def test_interest_art(self) -> None:
        self_s = self._make_self()
        analyze_personality(self_s, "user1", "I like to draw and paint")
        assert self_s.memory.update_user_traits.called

    def test_multiple_traits(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "lol thanks for the help!")
        assert "humorous" in traits
        assert "polite" in traits

    def test_returns_traits_list(self) -> None:
        traits = analyze_personality(self._make_self(), "user1", "lol")
        assert isinstance(traits, list)

    def test_update_user_traits_called_with_correct_user(self) -> None:
        self_s = self._make_self()
        analyze_personality(self_s, "user42", "lol thanks")
        call_args = self_s.memory.update_user_traits.call_args
        assert call_args is not None
        args, kwargs = call_args
        if kwargs:
            assert kwargs["user_id"] == "user42"
        elif args:
            assert args[0] == "user42"


class TestGetEmotionalTone:
    def test_happy(self) -> None:
        assert get_emotional_tone(None, 0.6) == "happy"

    def test_positive(self) -> None:
        assert get_emotional_tone(None, 0.3) == "positive"

    def test_neutral_zero(self) -> None:
        assert get_emotional_tone(None, 0.0) == "neutral"

    def test_neutral_slightly_positive(self) -> None:
        assert get_emotional_tone(None, 0.1) == "neutral"

    def test_neutral_slightly_negative(self) -> None:
        assert get_emotional_tone(None, -0.1) == "neutral"

    def test_negative(self) -> None:
        assert get_emotional_tone(None, -0.3) == "negative"

    def test_sad(self) -> None:
        assert get_emotional_tone(None, -0.6) == "sad"

    def test_boundary_happy(self) -> None:
        assert get_emotional_tone(None, 0.5) == "positive"
        assert get_emotional_tone(None, 0.51) == "happy"

    def test_boundary_sad(self) -> None:
        assert get_emotional_tone(None, -0.5) == "negative"
        assert get_emotional_tone(None, -0.51) == "sad"

    def test_boundary_positive(self) -> None:
        assert get_emotional_tone(None, 0.2) == "neutral"
        assert get_emotional_tone(None, 0.21) == "positive"


class TestDetectTopic:
    def test_gaming(self) -> None:
        assert detect_topic(None, "lets play some games") == "gaming"

    def test_anime(self) -> None:
        assert detect_topic(None, "I love anime") == "anime"

    def test_music(self) -> None:
        assert detect_topic(None, "listen to this song") == "music"

    def test_food(self) -> None:
        assert detect_topic(None, "I love cooking") == "food"

    def test_work(self) -> None:
        assert detect_topic(None, "got a meeting at work") == "work"

    def test_school(self) -> None:
        assert detect_topic(None, "I go to school") == "school"

    def test_movies(self) -> None:
        assert detect_topic(None, "watching a movie tonight") == "movies"

    def test_sports(self) -> None:
        assert detect_topic(None, "basketball is fun") == "sports"

    def test_no_topic(self) -> None:
        assert detect_topic(None, "the sky is blue") is None

    def test_first_topic_wins(self) -> None:
        assert detect_topic(None, "I play games and listen to music") == "gaming"

    def test_empty_string(self) -> None:
        assert detect_topic(None, "") is None

    def test_case_insensitive(self) -> None:
        assert detect_topic(None, "I Love Gaming") == "gaming"

    def test_steam_keyword(self) -> None:
        assert detect_topic(None, "steam sale is on") == "gaming"

    def test_netflix_keyword(self) -> None:
        assert detect_topic(None, "netflix has new shows") == "movies"

    def test_gym_keyword(self) -> None:
        assert detect_topic(None, "going to the gym") == "sports"

    def test_multiple_keywords_same_topic(self) -> None:
        assert detect_topic(None, "steam xbox ps5 nintendo") == "gaming"
