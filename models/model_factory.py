"""
Model Factory - Creates appropriate model connector based on configuration.
This is the ONLY place where specific connectors are imported.
"""
import os
from typing import Dict, Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import logger
from .model_interface import ModelInterface


loaded_models: Dict[str, ModelInterface] = {}

def get_model_connector(
    provider: Optional[str] = None,
    model_name: Optional[str] = None
) -> ModelInterface:
    """
    Factory function to create model connectors.
    Returns appropriate connector based on LLM_PROVIDER env variable.
    
    Args:
        provider: Override provider (otherwise uses LLM_PROVIDER env var). If not provided, defaults to 'vllm'.
        model_name: Model name/identifier
    
    Returns:
        ModelInterface implementation
    
    Raises:
        ValueError: If provider is unknown
        ImportError: If required connector module is not available
    
    Supported Providers:
        - lmstudio: LM Studio (OpenAI-compatible API)
        - vllm: vLLM (future - TIER 6)
        - sglang: SGLang (OpenAI-compatible API)
        - safetensors: Direct safetensors loading (future - TIER 6)
        - openai: OpenAI API
        - custom: Custom OpenAI-compatible endpoint
    """
    provider = provider or os.getenv("LLM_PROVIDER", "vllm")
    provider = provider.lower().strip()
    
    logger.info(f"🏭 Model factory: Creating connector for provider '{provider}'")
    
    # vLLM (default)
    if provider in ("vllm", "openai", "custom"):
        from models.vllm_connector import VLLMConnector
        return VLLMConnector(model_name)
    
    # LM Studio
    elif provider == "lmstudio":
        from models.lm_studio_connector import LMStudioConnector
        return LMStudioConnector(model_name)
    
    # SGLang
    elif provider == "sglang":
        from models.sglang_connector import SGLangConnector
        return SGLangConnector(model_name)
    
    # Safetensors direct loading (TIER 6 - future)
    elif provider == "safetensors":
        try:
            from models.safetensors_connector import SafetensorsConnector
            return SafetensorsConnector(model_name)
        except ImportError:
            raise ImportError(
                "Safetensors connector not implemented yet. "
                "This will be added in TIER 6. "
                "For now, use provider='lmstudio'"
            )
    
    else:
        raise ValueError(
            f"Unknown provider: '{provider}'. "
            f"Supported: vllm, sglang, safetensors"
        )


def get_available_providers() -> dict:
    """
    Get list of available providers and their status.
    
    Returns:
        Dict mapping provider names to availability status
    """
    providers = {
        'vllm': True,
        'sglang': True,
    }
    
    try:
        from models.safetensors_connector import SafetensorsConnector
        providers['safetensors'] = True
    except ImportError:
        providers['safetensors'] = False
    
    return providers


def get_loaded_models() -> Dict[str, ModelInterface]:
    """Get dictionary of all currently loaded models."""
    return loaded_models.copy()


def load_model_if_needed(model_name: str, temperature: Optional[float] = None, top_p: Optional[float] = None) -> ModelInterface:
    """
    Load a model if it's not already loaded, or return existing instance.
    
    Args:
        model_name: Name of model to load
        temperature: Optional temperature override
        top_p: Optional top_p override
    
    Returns:
        Loaded model instance
    """
    global loaded_models
    
    if model_name in loaded_models:
        connector = loaded_models[model_name]
        if temperature is not None or top_p is not None:
            # Update params if needed
            connector.load_model(temperature=temperature, top_p=top_p)
        return connector
    
    # Create new connector
    connector = get_model_connector(model_name=model_name)
    connector.load_model(temperature=temperature, top_p=top_p)
    loaded_models[model_name] = connector
    logger.info(f"✅ Model loaded and cached: {model_name}")
    
    return connector


def unload_model(model_name: str) -> bool:
    """
    Unload a specific model from memory.
    
    Args:
        model_name: Name of model to unload
        
    Returns:
        True if model was unloaded, False if it wasn't loaded
    """
    global loaded_models
    
    if model_name not in loaded_models:
        return False
        
    try:
        # Clean up resources
        connector = loaded_models[model_name]
        connector.client = None
        connector.adapter = None
        del loaded_models[model_name]
        logger.info(f"🗑️ Model unloaded from cache: {model_name}")
        return True
    except Exception as e:
        logger.error(f"❌ Error unloading model {model_name}: {e}")
        return False


def unload_all_models():
    """Unload all cached models."""
    global loaded_models
    
    for model_name in list(loaded_models.keys()):
        unload_model(model_name)
    
    loaded_models.clear()
    logger.info("🧹 All models unloaded from cache")

# def get_available_models_sorted(timeout_seconds: int = 5) -> Dict[str, Optional[List[str]]]:
#     """
#     Get models from LM Studio with smallest/largest detection.
    
#     Returns:
#         Dict with 'all', 'smallest', 'largest'
#     """
#     try:
#         from models.lm_studio_server_controller import get_lm_studio_controller
        
#         controller = get_lm_studio_controller()
        
#         # Get both loaded and available models
#         loaded = controller.list_loaded_models()
#         available = controller.list_available_models_on_disk()
        
#         # Combine (prefer loaded, add available)
#         all_models = []
#         seen = set()
        
#         for model in loaded:
#             identifier = model.get('identifier', model.get('path'))
#             if identifier:
#                 all_models.append(identifier)
#                 seen.add(identifier)
        
#         for model in available:
#             path = model['path']
#             if path not in seen:
#                 all_models.append(path)
#                 seen.add(path)
        
#         # Sort by parameter count heuristic
#         def extract_param_count(model_name):
#             import re
#             matches = re.findall(r'(\d+)[bBmM]', model_name.lower())
#             if matches:
#                 return int(matches[0])
#             return 0
        
#         sorted_models = sorted(all_models, key=extract_param_count)
        
#         # Get configured overrides
#         env_smallest = os.getenv("LLM_SMALLEST_MODEL")
#         env_largest = os.getenv("LLM_LARGEST_MODEL")
        
#         smallest = runtime_model_overrides.get('smallest') or env_smallest
#         largest = runtime_model_overrides.get('largest') or env_largest
        
#         # Auto-detect if not configured
#         if not smallest and sorted_models:
#             smallest = sorted_models[0]
#             logger.info(f"🎯 Auto-detected smallest: {smallest}")
        
#         if not largest and sorted_models:
#             largest = sorted_models[-1]
#             logger.info(f"🎯 Auto-detected largest: {largest}")
        
#         return {
#             'all': sorted_models,
#             'smallest': smallest,
#             'largest': largest
#         }
    
#     except Exception as e:
#         logger.error(f"❌ Error getting models: {e}")
#         import traceback
#         logger.error(traceback.format_exc())
#         return {
#             'all': [],
#             'smallest': None,
#             'largest': None
#         }