"""
LM Studio Connector - OpenAI-compatible API implementation.
Refactored from llama_connector.py to implement ModelInterface.
"""
import os
import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union
from openai import OpenAI
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from serin.state.logger import logger
from .interface import ModelInterface
from .adapter import ModelAdapter


class LMStudioConnector(ModelInterface):
    """
    LM Studio connector using OpenAI-compatible API.
    Works with any model loaded in LM Studio.
    """
    
    def __init__(self, model_name: Optional[str] = None) -> None:
        """
        Initialize LM Studio connector.
        
        Args:
            model_name: Model identifier or special selector (__SMALLEST__, __LARGEST__)
        """
        # Read configuration from environment
        self.base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
        self.api_key = os.getenv("LLM_API_KEY", "lm-studio")
        
        # Model configuration
        self.model_name = model_name or os.getenv("LLM_MODEL", None)
        self._model_selection_mode = None
        if self.model_name in ["__SMALLEST__", "__LARGEST__"]:
            self._model_selection_mode = self.model_name
            self.model_name = None  # Will be set during load_model
        
        # Generation parameters
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.75"))
        self.top_p = float(os.getenv("LLM_TOP_P", "0.9"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "400"))
        
        # OpenAI client and model adapter
        self.client: Optional[OpenAI] = None
        self.adapter: Optional[ModelAdapter] = None
        
        logger.info(f"🔌 LM Studio connector initialized - Base URL: {self.base_url}")
    
    def load_model(
        self,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        force_model_name: Optional[str] = None
    ) -> None:
        """
        Initialize OpenAI client and detect/load model.
        
        Args:
            temperature: Override default temperature
            top_p: Override default top_p
            force_model_name: Force a specific model to load
        """
        # Update parameters if provided
        if temperature is not None:
            self.temperature = temperature
        if top_p is not None:
            self.top_p = top_p
        
        # Initialize OpenAI client
        try:
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key
            )
            # Test connection immediately
            self.client.models.list()
        except Exception as e:
            logger.error(f" Failed to connect to LM Studio API: {e}")
            raise RuntimeError(f"Could not connect to LM Studio at {self.base_url}. Is it running?")
        
        try:
            # Get list of available models
            models = self.client.models.list()
            available_models = [model.id for model in models.data]
            
            if not available_models:
                raise RuntimeError("No models available in LM Studio. Please load a model first.")
                
            logger.info(f" Found {len(available_models)} models in LM Studio")
            for model in available_models:
                logger.info(f"   • {model}")
            
            # Force specific model if requested
            if force_model_name:
                if force_model_name not in available_models:
                    raise ValueError(f"Requested model '{force_model_name}' not available in LM Studio")
                self.model_name = force_model_name
                logger.info(f" Forced model selection: {self.model_name}")
                return
            
            # Handle smart model selection (__SMALLEST__ / __LARGEST__)
            if self._model_selection_mode:
                # First check environment variables
                env_smallest = os.getenv("LLM_SMALLEST_MODEL")
                env_largest = os.getenv("LLM_LARGEST_MODEL")
                
                if self._model_selection_mode == "__SMALLEST__" and env_smallest:
                    if env_smallest in available_models:
                        self.model_name = env_smallest
                        logger.info(f" Using SMALLEST model from ENV: {self.model_name}")
                        return
                elif self._model_selection_mode == "__LARGEST__" and env_largest:
                    if env_largest in available_models:
                        self.model_name = env_largest
                        logger.info(f" Using LARGEST model from ENV: {self.model_name}")
                        return
                
                # Sort models by parameter count (if available in name)
                def extract_param_count(model_name):
                    matches = re.findall(r'(\d+)[bm]', model_name.lower())
                    return int(matches[0]) if matches else 0
                
                sorted_models = sorted(available_models, key=extract_param_count)
                
                if self._model_selection_mode == "__SMALLEST__":
                    self.model_name = sorted_models[0]
                    logger.info(f" Selected SMALLEST model: {self.model_name}")
                else:  # __LARGEST__
                    self.model_name = sorted_models[-1]
                    logger.info(f" Selected LARGEST model: {self.model_name}")
            
            # Auto-detect model if still not specified
            if self.model_name is None:
                self.model_name = available_models[0]
                logger.info(f" Auto-detected model: {self.model_name}")
                if len(available_models) > 1:
                    logger.info(f"   Other available: {', '.join(available_models[1:])}")
            
        except Exception as e:
            logger.error(f" Failed to detect/select model: {e}")
            raise
        
        # Initialize model adapter for format handling
        self.adapter = ModelAdapter(self.model_name)
        
        logger.info(
            f" LM Studio ready - Model: {self.model_name} ({self.adapter.get_model_type()}), "
            f"Temp: {self.temperature}, Top-P: {self.top_p}"
        )
    
    def blocking_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Blocking chat completion.
        
        Args:
            messages: Chat messages
            temperature: Override temperature
            max_tokens: Override max tokens
            stop: Stop sequences
            **kwargs: Additional parameters
        
        Returns:
            Generated text
        """
        if self.client is None or self.adapter is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")
        
        # Format messages (adapter handles model-specific formatting if needed)
        formatted_messages = self.adapter.format_messages(messages)
        
        # Get model-specific stop tokens
        model_stop_tokens = self.adapter.get_stop_tokens()
        if stop:
            model_stop_tokens.extend(stop)
        
        # Prepare parameters
        params = {
            "model": self.model_name,
            "messages": formatted_messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
            "stream": False
        }
        
        if model_stop_tokens:
            params["stop"] = model_stop_tokens
        
        params.update(kwargs)
        
        try:
            response = self.client.chat.completions.create(**params)
            raw_text = response.choices[0].message.content
            
            # Clean response with model adapter
            cleaned = self.adapter.clean_response(raw_text)
            
            return cleaned
            
        except Exception as e:
            logger.error(f" Error during chat completion: {e}")
            raise
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """Async wrapper for chat_completion."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.blocking_chat_completion(messages, temperature, max_tokens, stop, **kwargs)
        )
    
    def blocking_send_input(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Blocking completion (legacy support).
        
        Args:
            prompt: Input prompt
            temperature: Override temperature
            max_tokens: Override max tokens
            stop: Stop sequences
            **kwargs: Additional parameters
        
        Returns:
            Generated text
        """
        if self.client is None or self.adapter is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")
        
        # Get model-specific stop tokens
        model_stop_tokens = self.adapter.get_stop_tokens()
        if stop:
            model_stop_tokens.extend(stop)
        
        params = {
            "model": self.model_name,
            "prompt": prompt,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
            "stream": False
        }
        
        if model_stop_tokens:
            params["stop"] = model_stop_tokens
        
        params.update(kwargs)
        
        try:
            response = self.client.completions.create(**params)
            raw_text = response.choices[0].text
            
            # Clean response
            cleaned = self.adapter.clean_response(raw_text)
            
            return cleaned
            
        except Exception as e:
            logger.error(f" Error during completion: {e}")
            raise
    
    async def send_input(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """Async wrapper for send_input."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.blocking_send_input(prompt, temperature, max_tokens, stop, **kwargs)
        )
    
    def get_available_models(self) -> List[str]:
        """
        Get list of models currently available in LM Studio.
        
        Returns:
            List of model names
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call load_model() first.")
            
        try:
            models = self.client.models.list()
            return [model.id for model in models.data]
        except Exception as e:
            logger.error(f" Failed to get available models: {e}")
            return []

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get model information.
        
        Returns:
            Dict with model details
        """
        info = {
            'model_name': self.model_name,
            'model_type': self.adapter.get_model_type() if self.adapter else 'unknown',
            'provider': 'lmstudio',
            'base_url': self.base_url,
            'temperature': self.temperature,
            'top_p': self.top_p,
            'max_tokens': self.max_tokens,
            'available_models': []
        }
        
        # Add list of available models if client is initialized
        if self.client:
            try:
                info['available_models'] = self.get_available_models()
            except:
                pass
                
        return info
