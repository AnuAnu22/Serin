"""Serin model layer — LLM connectors, adapter, factory."""
from models.factory import get_model_connector
from models.interface import ModelInterface

__all__ = ["get_model_connector", "ModelInterface"]
