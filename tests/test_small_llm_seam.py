"""SMALL_LLM_* configuration seam — the supporting ("small") LLM used by
MemoryWriteStage for per-message fact/belief extraction.

Pins the contract end-to-end WITHOUT any live model:

  1. BotConfig aliases SMALL_LLM_* to the main LLM settings when the env keys
     are unset (the historical single-model behavior — nothing changes unless
     the operator opts in).
  2. When set, SMALL_LLM_* override independently, and an unset key keeps its
     main-LLM fallback (partial opt-in is legal: dedicated model on the same
     endpoint).
  3. The small connector is a DISTINCT cached slot from the main connector
     (`__small__` vs `__default__`) so a dedicated endpoint never evicts or
     thrashes the chat model's cache entry.
  4. serin_di exposes exactly one accessor and it returns that same cached
     instance (Rule-5 seam; consumers never import the factory module).

Determinism note: these tests assert state-caused wiring only. No RNG is
involved anywhere in this seam (SERIN_VISION "causality, not performance").
"""
from __future__ import annotations

from typing import Any

import pytest

# --- Helpers ---------------------------------------------------------------


def _fresh_config(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Reset the BotConfig singleton under the CURRENT environment and install
    the fresh instance as the module-global ``config`` (so LLMConnector, which
    reads the global, sees it too). Resets the singleton the same way
    tests/test_config_creator.py does; monkeypatch restores everything after
    each test. Call :func:`_prepare_config_env` (+ any extra setenv) BEFORE
    calling this."""
    import serin.d1_4_config_base.d2_1_base_config as base_config_module

    monkeypatch.setattr(base_config_module.BotConfig, "_instance", None)
    fresh = base_config_module.BotConfig()
    monkeypatch.setattr(base_config_module, "config", fresh)
    return fresh


def _prepare_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the main-LLM env and clear any SMALL_LLM_* overrides."""
    monkeypatch.delenv("SMALL_LLM_MODEL", raising=False)
    monkeypatch.delenv("SMALL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SMALL_LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "main-chat-model")
    monkeypatch.setenv("LLM_BASE_URL", "http://main:8080/v1")
    monkeypatch.setenv("LLM_API_KEY", "main-key")


# --- Tests -----------------------------------------------------------------


def test_small_llm_keys_alias_main_llm_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset SMALL_LLM_* falls back to the main LLM settings (historical behavior)."""
    _prepare_config_env(monkeypatch)
    cfg = _fresh_config(monkeypatch)
    assert cfg.SMALL_LLM_MODEL == "main-chat-model"
    assert cfg.SMALL_LLM_BASE_URL == "http://main:8080/v1"
    assert cfg.SMALL_LLM_API_KEY == "main-key"


def test_small_llm_keys_override_independently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each SMALL_LLM_* key overrides its main counterpart; partial opt-in is
    legal (e.g., dedicated extraction model on the SAME llama-swap endpoint)."""
    _prepare_config_env(monkeypatch)
    monkeypatch.setenv("SMALL_LLM_MODEL", "tiny-extractor")
    monkeypatch.delenv("SMALL_LLM_BASE_URL", raising=False)  # keep main fallback
    monkeypatch.setenv("SMALL_LLM_API_KEY", "small-key")
    cfg = _fresh_config(monkeypatch)
    assert cfg.SMALL_LLM_MODEL == "tiny-extractor"
    assert cfg.SMALL_LLM_BASE_URL == "http://main:8080/v1"
    assert cfg.SMALL_LLM_API_KEY == "small-key"


def test_small_llm_connector_uses_distinct_cache_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """The small connector lives in its own `__small__` cache slot — distinct
    from the main `__default__` slot — so the two never thrash each other."""
    from serin.d1_3_state_core.d2_3_model_system.d3_2_system_connector import (
        LLMConnector,
    )
    from serin.d1_3_state_core.d2_3_model_system.d3_3_system_factory import (
        get_loaded_models,
        get_model_connector,
        get_small_llm_connector,
    )

    small = get_small_llm_connector()
    try:
        assert isinstance(small, LLMConnector)
        # Distinct object identity from the main default connector.
        main = get_model_connector()
        assert small is not main
        slots = get_loaded_models()
        assert "__small__" in slots
        assert slots["__small__"] is small
        # Repeat calls are stable (cached), matching get_model_connector semantics.
        assert get_small_llm_connector() is small
    finally:
        # Never leak the test connector into other tests' factory state.
        from serin.d1_3_state_core.d2_3_model_system import (
            d3_3_system_factory as factory,
        )

        factory.loaded_models.pop("__small__", None)


def test_small_llm_connector_reads_override_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """With SMALL_LLM_* set, the constructed connector points at the small
    endpoint/model, not the main one."""
    from serin.d1_3_state_core.d2_3_model_system import d3_3_system_factory as factory

    _prepare_config_env(monkeypatch)
    monkeypatch.setenv("SMALL_LLM_MODEL", "tiny-extractor")
    monkeypatch.setenv("SMALL_LLM_BASE_URL", "http://small:8081/v1")
    monkeypatch.setenv("SMALL_LLM_API_KEY", "small-key")
    cfg = _fresh_config(monkeypatch)
    try:
        connector = factory.LLMConnector(
            model_name=cfg.SMALL_LLM_MODEL,
            base_url=cfg.SMALL_LLM_BASE_URL,
            api_key=cfg.SMALL_LLM_API_KEY,
        )
        assert connector.model_name == "tiny-extractor"
        assert connector.base_url == "http://small:8081/v1"
    finally:
        factory.loaded_models.pop("__small__", None)


def test_serin_di_returns_the_cached_small_connector() -> None:
    """The Rule-5 accessor hands out the same cached instance the factory holds;
    gateway/pipeline code never imports the model-system module directly."""
    from serin.d1_1_serin_di import get_small_llm_connector
    from serin.d1_3_state_core.d2_3_model_system import d3_3_system_factory as factory

    try:
        via_di = get_small_llm_connector()
        via_factory = factory.get_small_llm_connector()
        assert via_di is via_factory
    finally:
        factory.loaded_models.pop("__small__", None)
