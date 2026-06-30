# File: llama_connector.py
import os
import re
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import logger
from openai import OpenAI
from typing import Optional, List, Dict, Any

class LlamaConnector:
    """
    Universal LLM connector that works with:
    - LM Studio (local models via OpenAI-compatible API)
    - OpenAI API (GPT models)
    - Any OpenAI-compatible API
    
    Configuration via environment variables:
    - LLM_PROVIDER: "lmstudio" or "openai" (default: "lmstudio")
    - LLM_BASE_URL: Base URL for API (default: "http://localhost:1234/v1" for LM Studio)
    - LLM_API_KEY: API key (default: "lm-studio" for LM Studio, required for OpenAI)
    - LLM_MODEL: Model identifier (default: auto-detect for LM Studio)
    - LLM_TEMPERATURE: Default temperature (default: 0.7)
    - LLM_TOP_P: Default top_p (default: 0.9)
    - LLM_MAX_TOKENS: Default max tokens (default: 768)
    """
    
    def __init__(self, model_name: Optional[str] = None):
        # Read configuration from environment
        self.provider = os.getenv("LLM_PROVIDER", "lmstudio").lower()
        
        # Set base URL based on provider
        if self.provider == "lmstudio":
            default_base_url = "http://localhost:1234/v1"
            default_api_key = "lm-studio"
        else:  # openai or custom
            default_base_url = "https://api.openai.com/v1"
            default_api_key = os.getenv("OPENAI_API_KEY", "")
        
        self.base_url = os.getenv("LLM_BASE_URL", default_base_url)
        self.api_key = os.getenv("LLM_API_KEY", default_api_key)
        
        # Model configuration
        self.model_name = model_name or os.getenv("LLM_MODEL", None)
        self._model_selection_mode = None
        if self.model_name in ["__SMALLEST__", "__LARGEST__"]:
            self._model_selection_mode = self.model_name
            self.model_name = None  # Will be set during load_model

        # Generation parameters
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.75"))  # Increased from 0.7
        self.top_p = float(os.getenv("LLM_TOP_P", "0.9"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "400"))  # Reduced from 768
        
        # Initialize client
        self.client: Optional[OpenAI] = None
        
        logger.info(f"LLM Connector initialized - Provider: {self.provider}, Base URL: {self.base_url}")
    
    def get_available_models_sorted(self) -> Dict[str, Any]:
        """
        Get available models sorted by parameter size.
        
        Returns:
            Dict with 'smallest' and 'largest' model names
        """
        try:
            models = self.client.models.list()
            available_models = [model.id for model in models.data]
            
            # Parse billion parameters from model names
            def extract_size(model_name: str) -> float:
                match = re.search(r'(\d+(?:\.\d+)?)[bB]', model_name)
                if match:
                    return float(match.group(1))
                # Default to large number if no size found (vision/special models)
                return 999.0
            
            # Filter out non-instruct models (embedding, vision)
            instruct_models = [
                m for m in available_models 
                if 'instruct' in m.lower() and 'embed' not in m.lower()
            ]
            
            if not instruct_models:
                instruct_models = available_models  # Fallback
            
            # Sort by size
            sorted_models = sorted(instruct_models, key=extract_size)
            
            return {
                'smallest': sorted_models[0] if sorted_models else None,
                'largest': sorted_models[-1] if sorted_models else None,
                'all': sorted_models
            }
            
        except Exception as e:
            logger.error(f"Failed to get sorted models: {e}")
            return {'smallest': None, 'largest': None, 'all': []}

    def load_model(self, temperature: Optional[float] = None, top_p: Optional[float] = None) -> None:
        """
        Initialize the OpenAI client and detect available model.
        For LM Studio, this will auto-detect the loaded model.
        For OpenAI, you must specify the model name.
        """
        # Update parameters if provided
        if temperature is not None:
            self.temperature = temperature
        if top_p is not None:
            self.top_p = top_p
        
        # Initialize OpenAI client
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        
        # Handle smart model selection
        if self._model_selection_mode and self.model_name is None:
            # Check ENV overrides first
            env_smallest = os.getenv("LLM_SMALLEST_MODEL")
            env_largest = os.getenv("LLM_LARGEST_MODEL")

            if self._model_selection_mode == "__SMALLEST__" and env_smallest:
                self.model_name = env_smallest
                logger.info(f" Using SMALLEST model from ENV: {self.model_name}")
            elif self._model_selection_mode == "__LARGEST__" and env_largest:
                self.model_name = env_largest
                logger.info(f" Using LARGEST model from ENV: {self.model_name}")
            else:
                sorted_models = self.get_available_models_sorted()
                if self._model_selection_mode == "__SMALLEST__":
                    self.model_name = sorted_models['smallest']
                    logger.info(f" Selected SMALLEST model: {self.model_name}")
                elif self._model_selection_mode == "__LARGEST__":
                    self.model_name = sorted_models['largest']
                    logger.info(f" Selected LARGEST model: {self.model_name}")
                logger.info(f"Available models by size: {sorted_models['all']}")    

        # Auto-detect model if not specified (useful for LM Studio)
        if self.model_name is None:
            try:
                models = self.client.models.list()
                available_models = [model.id for model in models.data]
                
                if available_models:
                    self.model_name = available_models[0]
                    logger.info(f"Auto-detected model: {self.model_name}")
                    if len(available_models) > 1:
                        logger.info(f"Other available models: {', '.join(available_models[1:])}")
                else:
                    raise RuntimeError("No models available.")
            except Exception as e:
                logger.error(f"Failed to detect model: {e}")
                raise
        
        logger.info(
            f"LLM Client ready - Model: {self.model_name}, "
            f"Temperature: {self.temperature}, Top-P: {self.top_p}"
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
        Send a completion request (blocking).
        
        Args:
            prompt: The input prompt
            temperature: Override default temperature
            max_tokens: Override default max tokens
            stop: Stop sequences
            **kwargs: Additional parameters to pass to the API
        
        Returns:
            Generated text response
        """
        if self.client is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")
        
        # Prepare parameters
        params = {
            "model": self.model_name,
            "prompt": prompt,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
            "stream": False
        }
        
        # Add stop sequences if provided
        if stop:
            params["stop"] = stop
        
        # Add any additional parameters
        params.update(kwargs)
        
        try:
            response = self.client.completions.create(**params)
            return response.choices[0].text
        except Exception as e:
            logger.error(f"Error during completion: {e}")
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
    
    def blocking_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Send a chat completion request (blocking).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max tokens
            stop: Stop sequences
            **kwargs: Additional parameters (e.g., tools, tool_choice, response_format)
        
        Returns:
            Generated text response
        """
        if self.client is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")
        
        # Prepare parameters
        params = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
            "stream": False
        }
        
        # Add stop sequences if provided
        if stop:
            params["stop"] = stop
        
        # Add any additional parameters
        params.update(kwargs)
        
        try:
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error during chat completion: {e}")
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
    
    def blocking_stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Stream a chat completion (blocking generator).
        
        Yields:
            Text chunks as they arrive
        """
        if self.client is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")
        
        params = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
            "stream": True
        }
        
        if stop:
            params["stop"] = stop
        
        params.update(kwargs)
        
        try:
            stream = self.client.chat.completions.create(**params)
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            raise
    
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Async stream a chat completion.
        
        Yields:
            Text chunks as they arrive
        """
        loop = asyncio.get_running_loop()
        
        # Create a generator that yields chunks
        def sync_generator():
            return self.blocking_stream_chat(messages, temperature, max_tokens, stop, **kwargs)
        
        generator = await loop.run_in_executor(None, sync_generator)
        
        for chunk in generator:
            yield chunk
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embeddings for text.
        
        Args:
            text: Text to embed
        
        Returns:
            List of embedding values
        """
        if self.client is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")
        
        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    async def get_embedding_async(self, text: str) -> List[float]:
        """Async wrapper for get_embedding."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_embedding, text)