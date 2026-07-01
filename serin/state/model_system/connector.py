"""Single LLM connector for llama-swap / any OpenAI-compatible backend."""
import asyncio
import os
import sys
import threading
import time
from typing import Any

import httpx
from openai import OpenAI

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from serin.config.config import config
from serin.logger import logger

from .adapter import ModelAdapter
from .interface import ModelInterface


class LLMConnector(ModelInterface):
    """OpenAI-compatible HTTP connector — works with llama-swap, vLLM, etc."""

    RETRY_INTERVAL = 15

    def __init__(self, model_name: str | None = None) -> None:
        self.base_url = config.LLM_BASE_URL
        self.api_key = config.LLM_API_KEY
        self.model_name = model_name or config.LLM_MODEL or None
        self.temperature = config.LLM_TEMPERATURE
        self.top_p = config.LLM_TOP_P
        self.max_tokens = config.LLM_MAX_TOKENS
        self.enable_thinking = config.LLM_ENABLE_THINKING
        self.client: OpenAI | None = None
        self.adapter: ModelAdapter | None = None
        self._connected = False
        self._retry_thread: threading.Thread | None = None
        logger.info(f"LLM connector initialized - Base URL: {self.base_url}")

    def _try_connect(self) -> None:
        """Attempt a single connection and model detection."""
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0),
            max_retries=2,
        )
        self.client.models.list()

        models = self.client.models.list()
        available_models = [model.id for model in models.data]
        if not available_models:
            raise RuntimeError("No models available on endpoint. Load a model first.")

        if self.model_name:
            if self.model_name not in available_models:
                logger.warning(f"Model '{self.model_name}' not found. Available: {', '.join(available_models)}")
                self.model_name = available_models[0]
                logger.info(f"Auto-selected: {self.model_name}")
            else:
                logger.info(f"Using configured model: {self.model_name}")
        else:
            self.model_name = available_models[0]
            logger.info(f"Auto-detected model: {self.model_name}")

        if len(available_models) > 1:
            logger.info(f"Available: {', '.join(available_models)}")

        self.adapter = ModelAdapter(self.model_name)
        self._connected = True

    def _retry_loop(self) -> None:
        """Background thread: keep trying every RETRY_INTERVAL seconds until connected."""
        while not self._connected:
            time.sleep(self.RETRY_INTERVAL)
            try:
                self._try_connect()
                logger.success(f"LLM reconnected to {self.base_url}")
                logger.info(
                    f"LLM ready - Model: {self.model_name} ({self.adapter.get_model_type()}), "
                    f"Temp: {self.temperature}, Top-P: {self.top_p}"
                )
            except Exception:
                pass

    def load_model(
        self,
        temperature: float | None = None,
        top_p: float | None = None
    ) -> None:
        if temperature is not None:
            self.temperature = temperature
        if top_p is not None:
            self.top_p = top_p

        for attempt in range(3):
            try:
                self._try_connect()
                logger.info(
                    f"LLM ready - Model: {self.model_name} ({self.adapter.get_model_type()}), "
                    f"Temp: {self.temperature}, Top-P: {self.top_p}"
                )
                return
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"Connection attempt {attempt + 1}/3 failed: {e}. Retrying...")
                    time.sleep(1)
                else:
                    logger.error(f"Failed to connect after 3 attempts: {e}")
                    logger.info(f"Will keep retrying every {self.RETRY_INTERVAL}s in the background")

        if self._retry_thread is None or not self._retry_thread.is_alive():
            self._retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
            self._retry_thread.start()

    @property
    def is_connected(self) -> bool:
        return self._connected and self.client is not None and self.adapter is not None

    def blocking_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        **kwargs
    ) -> str:
        if self.client is None or self.adapter is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")

        formatted_messages = self.adapter.format_messages(messages)
        model_stop_tokens = self.adapter.get_stop_tokens()
        if stop:
            model_stop_tokens.extend(stop)

        params: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
            "stream": False
        }

        if self.adapter.get_model_type() in ("gemma", "deepseek"):
            extra = kwargs.pop("extra_body", {})
            extra["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
            params["extra_body"] = extra

        if model_stop_tokens:
            params["stop"] = model_stop_tokens

        params.update(kwargs)

        try:
            response = self.client.chat.completions.create(**params)
            raw_text = response.choices[0].message.content or ""
            return self.adapter.clean_response(raw_text)
        except Exception as e:
            logger.error(f" Chat completion error: {e}")
            raise

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
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
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        **kwargs
    ) -> str:
        if self.client is None or self.adapter is None:
            raise RuntimeError("Client not initialized. Call load_model() first.")

        model_stop_tokens = self.adapter.get_stop_tokens()
        if stop:
            model_stop_tokens.extend(stop)

        params: dict[str, Any] = {
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
            logger.error(f" Completion error: {e}")
            raise

    async def send_input(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        **kwargs
    ) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.blocking_send_input(prompt, temperature, max_tokens, stop, **kwargs)
        )

    def get_model_info(self) -> dict[str, Any]:
        return {
            'model_name': self.model_name,
            'model_type': self.adapter.get_model_type() if self.adapter else 'unknown',
            'provider': 'llama-swap',
            'base_url': self.base_url,
            'temperature': self.temperature,
            'top_p': self.top_p,
            'max_tokens': self.max_tokens,
        }
