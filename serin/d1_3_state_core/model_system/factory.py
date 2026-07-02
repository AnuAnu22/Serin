"""Model factory — creates LLMConnector pointing at llama-swap."""
from __future__ import annotations

from typing import Any

from .connector import LLMConnector
from .interface import ModelInterface

loaded_models: dict[str, ModelInterface] = {}

def get_model_connector(
    provider: str | None = None,
    model_name: str | None = None
) -> ModelInterface:
    """Create a single LLMConnector pointed at llama-swap (or any OpenAI-compatible endpoint)."""
    return LLMConnector(model_name)

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
