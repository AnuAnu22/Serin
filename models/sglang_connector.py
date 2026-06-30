"""
SGLang Connector - OpenAI-compatible API implementation for SGLang.
Uses the OpenAI Python client pointed at an SGLang server.
"""
import os
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union
from openai import OpenAI
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from serin.core.logger import logger
from .model_interface import ModelInterface
from .model_adapter import ModelAdapter


class SGLangConnector(ModelInterface):
    """
    SGLang connector using the OpenAI-compatible API.
    - Defaults base_url to the provided SGLang endpoint
    - Auto-selects the first available model if none specified
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        # Configuration
        self.base_url = os.getenv("SGLANG_BASE_URL", "http://localhost:30000/v1")
        self.api_key = os.getenv("SGLANG_API_KEY", "unused")

        # Model configuration
        self.model_name = model_name or os.getenv("LLM_MODEL", None)

        # Generation parameters
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.75"))
        self.top_p = float(os.getenv("LLM_TOP_P", "0.9"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "400"))

        # Client and adapter
        self.client: Optional[OpenAI] = None
        self.adapter: Optional[ModelAdapter] = None

        logger.info(f"🔌 SGLang connector initialized - Base URL: {self.base_url}")

    def load_model(
        self,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None
    ) -> None:
        """
        Initialize OpenAI client and detect/load model from SGLang.
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
            # Test connection
            self.client.models.list()
        except Exception as e:
            logger.error(f" Failed to connect to SGLang API: {e}")
            raise RuntimeError(f"Could not connect to SGLang at {self.base_url}. Is it running?")

        try:
            # Get list of available models
            models = self.client.models.list()
            available_models = [model.id for model in models.data]

            if not available_models:
                raise RuntimeError(" No models available on SGLang endpoint. Please load a model first.")

            # Validate configured model or auto-detect
            if self.model_name:
                # Check if configured model exists
                if self.model_name not in available_models:
                    # Check for placeholder patterns
                    if self.model_name.startswith('__') and self.model_name.endswith('__'):
                        logger.warning(f" Placeholder model '{self.model_name}' detected. Auto-selecting from available models.")
                        self.model_name = available_models[0]
                        logger.info(f" Auto-selected model: {self.model_name}")
                    else:
                        # Provide helpful error with available models
                        raise ValueError(
                            f" Configured model '{self.model_name}' not found on SGLang server.\n"
                            f"Available models: {', '.join(available_models)}\n"
                            f"Update LLM_MODEL in .env file or remove the setting for auto-selection."
                        )
                else:
                    logger.info(f" Using configured model: {self.model_name}")
            else:
                # Auto-detect model if not specified
                self.model_name = available_models[0]
                logger.info(f" Auto-detected model: {self.model_name}")
                
            # Show all available models
            if len(available_models) > 1:
                logger.info(f" Available models: {', '.join(available_models)}")

        except ValueError:
            # Re-raise ValueError (our custom error)
            raise
        except Exception as e:
            logger.error(f" Failed to detect/select model: {e}")
            raise RuntimeError(f"Could not communicate with SGLang server at {self.base_url}. Is it running and accessible?")

        # Initialize model adapter
        self.adapter = ModelAdapter(self.model_name)

        logger.info(
            f" SGLang ready - Model: {self.model_name} ({self.adapter.get_model_type()}), "
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
        if self.client is None or self.adapter is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")

        formatted_messages = self.adapter.format_messages(messages)
        model_stop_tokens = self.adapter.get_stop_tokens()
        if stop:
            model_stop_tokens.extend(stop)

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
            return self.adapter.clean_response(raw_text)
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
        if self.client is None or self.adapter is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")

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
            return self.adapter.clean_response(raw_text)
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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.blocking_send_input(prompt, temperature, max_tokens, stop, **kwargs)
        )

    def get_model_info(self) -> Dict[str, Any]:
        return {
            'model_name': self.model_name,
            'model_type': self.adapter.get_model_type() if self.adapter else 'unknown',
            'provider': 'sglang',
            'base_url': self.base_url,
            'temperature': self.temperature,
            'top_p': self.top_p,
            'max_tokens': self.max_tokens,
        }
