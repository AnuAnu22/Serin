"""Model factory — creates LLMConnector pointing at llama-swap."""
from __future__ import annotations

from typing import Any

from serin.d1_4_config_base.d2_1_base_config import config

from .d3_2_system_connector import LLMConnector
from .d3_4_system_interface import ModelInterface

loaded_models: dict[str, ModelInterface] = {}

def get_model_connector(
    model_name: str | None = None
) -> ModelInterface:
    """Return a cached LLMConnector, creating one if not yet cached for this model_name."""
    key = model_name or "__default__"
    if key not in loaded_models:
        loaded_models[key] = LLMConnector(model_name)
    return loaded_models[key]

def get_small_llm_connector() -> ModelInterface:
    """Connector for the supporting ("small") LLM used by memory fact/belief
    extraction. Cached separately from the main connector so a dedicated
    SMALL_LLM_* endpoint never evicts or thrashes the chat model's cache slot.
    Falls back to the main LLM settings when SMALL_LLM_* is unset (config
    aliases them), matching the historical single-model behavior."""
    key = "__small__"
    if key not in loaded_models:
        loaded_models[key] = LLMConnector(
            model_name=config.SMALL_LLM_MODEL,
            base_url=config.SMALL_LLM_BASE_URL,
            api_key=config.SMALL_LLM_API_KEY,
        )
    return loaded_models[key]


def get_available_providers() -> dict[str, bool]:
    """Return available providers (always just llama-swap)."""
    return {'llama-swap': True}

def get_loaded_models() -> dict[str, ModelInterface]:
    return loaded_models.copy()

def load_model_if_needed(
    model_name: str,
    temperature: float | None = None,
    top_p: float | None = None
) -> ModelInterface:
    global loaded_models
    if model_name in loaded_models:
        connector = loaded_models[model_name]
        if temperature is not None or top_p is not None:
            connector.load_model(temperature=temperature, top_p=top_p)
        return connector
    connector = get_model_connector(model_name=model_name)
    connector.load_model(temperature=temperature, top_p=top_p)
    loaded_models[model_name] = connector
    return connector

def unload_model(model_name: str) -> bool:
    global loaded_models
    if model_name not in loaded_models:
        return False
    connector: Any = loaded_models[model_name]
    connector.client = None
    connector.adapter = None
    del loaded_models[model_name]
    return True

def unload_all_models() -> None:
    global loaded_models
    for model_name in list(loaded_models.keys()):
        unload_model(model_name)
    loaded_models.clear()
