"""Tests for BotConfig.CREATOR_IDS parsing."""
from typing import Any

import pytest


def _fresh_config(monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> Any:
    """Build a fresh BotConfig with CREATOR_IDS set (or unset) in the env."""
    from serin.d1_4_config_base import d2_1_base_config as mod

    if env_value is None:
        monkeypatch.delenv("CREATOR_IDS", raising=False)
    else:
        monkeypatch.setenv("CREATOR_IDS", env_value)
    # Reset the singleton so __init__ re-reads the environment;
    # monkeypatch restores the original instance after the test.
    monkeypatch.setattr(mod.BotConfig, "_instance", None)
    return mod.BotConfig()


def test_default_creator_id_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _fresh_config(monkeypatch, None)
    assert cfg.CREATOR_IDS == frozenset({"1378682870876340395"})


def test_empty_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _fresh_config(monkeypatch, "")
    assert cfg.CREATOR_IDS == frozenset({"1378682870876340395"})


def test_parses_comma_separated_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _fresh_config(monkeypatch, "111, 222 ,333")
    assert cfg.CREATOR_IDS == frozenset({"111", "222", "333"})


def test_single_id(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _fresh_config(monkeypatch, "424242")
    assert cfg.CREATOR_IDS == frozenset({"424242"})


def test_malformed_entries_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _fresh_config(monkeypatch, "111,not-an-id,222,")
    assert cfg.CREATOR_IDS == frozenset({"111", "222"})


def test_creator_ids_is_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _fresh_config(monkeypatch, "111")
    assert isinstance(cfg.CREATOR_IDS, frozenset)


def test_voice_behavior_seeds_creator_ids_from_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    from serin.d1_2_gateway_io.d2_2_voice_system.d3_1_system_audio.d4_1_audio_process import (
        d5_2_voice_behavior as vb_mod,
    )
    from serin.d1_4_config_base.d2_1_base_config import config

    monkeypatch.setattr(vb_mod, "get_logger", lambda: MagicMock())
    vbm = vb_mod.VoiceBehaviorManager(
        personality=MagicMock(), voice_listener=MagicMock()
    )
    assert vbm.creator_user_ids == set(config.CREATOR_IDS)
