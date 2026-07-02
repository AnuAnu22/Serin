"""
serin.core.config
-----------------
BotConfig singleton — loads environment variables via python-dotenv and
provides typed access to all configuration keys.

Responsibilities:
- Read DISCORD_TOKEN, LLM_MODEL, QDRANT_HOST, etc. from .env
- Provide defaults for all optional settings
- Validate required config at import time

Key classes:
- BotConfig: singleton accessed via `config` module-level instance
"""
from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class BotConfig:
    _instance: BotConfig | None = None

    def __new__(cls) -> BotConfig:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._initialized: bool = True

        # --- Core Settings ---
        self.DISCORD_TOKEN: str | None = os.getenv('DISCORD_TOKEN')
        self.DEBUG_MODE: bool = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        self.TRACE_MESSAGES: bool = os.getenv('TRACE_MESSAGES', 'true').lower() == 'true'
        self.MAINTENANCE_INTERVAL_HOURS: int = int(os.getenv('MAINTENANCE_INTERVAL_HOURS', '24'))
        self.CONTROL_PANEL_PORT: int = int(os.getenv('CONTROL_PANEL_PORT', '8081'))
        self.CONTROL_PANEL_KEY: str = os.getenv('CONTROL_PANEL_KEY', '')

        # --- Feature Flags ---
        self.ENABLE_VOICE: bool = os.getenv('ENABLE_VOICE', 'true').lower() == 'true'
        self.ENABLE_TTS: bool = os.getenv('ENABLE_TTS', 'true').lower() == 'true'

        # --- Voice Receiver Mode ---
        # "rust" (default): Rust songbird Driver — DAVE-compatible, no gateway conflict
        # "pycord": discord.py AudioSink — simpler but lacks DAVE support
        self.VOICE_RECEIVER_MODE: str = os.getenv('VOICE_RECEIVER_MODE', 'rust').lower()

        # --- Rust Binary Path ---
        self.RUST_VOICE_RECEIVER_PATH: str = os.getenv(
            'RUST_VOICE_RECEIVER_PATH',
            os.path.join(os.path.dirname(__file__), 'voice', 'rust_receiver', 'target', 'release', 'voice_receiver')
        )

        # --- Qdrant Settings ---
        self.QDRANT_HOST: str = os.getenv('QDRANT_HOST', 'localhost')
        self.QDRANT_PORT: int = int(os.getenv('QDRANT_PORT', '6333'))
        self.QDRANT_USE_DOCKER: bool = os.getenv('QDRANT_USE_DOCKER', 'false').lower() == 'true'
        self.QDRANT_DOCKER_CONTAINER_NAME: str = os.getenv('QDRANT_DOCKER_CONTAINER_NAME', 'serin-qdrant')
        self.QDRANT_DOCKER_IMAGE: str = os.getenv('QDRANT_DOCKER_IMAGE', 'qdrant/qdrant:latest')

        # --- Model Settings (llama-swap / OpenAI-compatible backend) ---
        self.LLM_MODEL: str = os.getenv('LLM_MODEL', 'Qwen/Qwen2.5-7B-Instruct')
        self.LLM_BASE_URL: str = os.getenv('LLM_BASE_URL', 'http://localhost:8080/v1')
        self.LLM_API_KEY: str = os.getenv('LLM_API_KEY', 'unused')
        self.LLM_SUPPORTS_VISION: bool = os.getenv('LLM_SUPPORTS_VISION', 'false').lower() == 'true'
        self.VISION_MODEL: str = os.getenv('VISION_MODEL', 'smolvlm256m')
        self.LLM_SUPPORTS_AUDIO: bool = os.getenv('LLM_SUPPORTS_AUDIO', 'false').lower() == 'true'
        # --- LLM generation parameters ---
        self.LLM_TEMPERATURE: float = float(os.getenv('LLM_TEMPERATURE', '0.75'))
        self.LLM_TOP_P: float = float(os.getenv('LLM_TOP_P', '0.9'))
        self.LLM_MAX_TOKENS: int = int(os.getenv('LLM_MAX_TOKENS', '400'))
        self.LLM_ENABLE_THINKING: bool = os.getenv('LLM_ENABLE_THINKING', 'false').lower() == 'true'

        # --- Debug / Logging ---
        self.DEBUG_MEMORY: bool = os.getenv('DEBUG_MEMORY', 'false').lower() == 'true'
        self.DEBUG_LLM: bool = os.getenv('DEBUG_LLM', 'false').lower() == 'true'
        self.LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'DEBUG').upper()
        self.LOG_FORMAT: str = os.getenv('LOG_FORMAT', 'text').lower()

        # --- Allowed Channels ---
        allowed_ids_str: str = os.getenv('ALLOWED_CHANNEL_IDS', '')
        self.ALLOWED_CHANNEL_IDS: set[int] = set()
        if allowed_ids_str:
            try:
                self.ALLOWED_CHANNEL_IDS = {int(x.strip()) for x in allowed_ids_str.split(',') if x.strip()}
            except ValueError:
                logger.warning(" Invalid ALLOWED_CHANNEL_IDS in .env")

        # --- Personality Settings (Runtime only for now) ---
        self.PERSONALITY: dict[str, float] = {
            'energy': 0.5,
            'sass': 0.5,
            'engagement': 0.5
        }

        logger.info(" BotConfig initialized")

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for API"""
        return {
            'DEBUG_MODE': self.DEBUG_MODE,
            'TRACE_MESSAGES': self.TRACE_MESSAGES,
            'MAINTENANCE_INTERVAL_HOURS': self.MAINTENANCE_INTERVAL_HOURS,
            'ENABLE_VOICE': self.ENABLE_VOICE,
            'ENABLE_TTS': self.ENABLE_TTS,
            'VOICE_RECEIVER_MODE': self.VOICE_RECEIVER_MODE,
            'LLM_MODEL': self.LLM_MODEL,
            'LLM_BASE_URL': self.LLM_BASE_URL,
            'LLM_TEMPERATURE': self.LLM_TEMPERATURE,
            'LLM_TOP_P': self.LLM_TOP_P,
            'LLM_MAX_TOKENS': self.LLM_MAX_TOKENS,
            'LLM_ENABLE_THINKING': self.LLM_ENABLE_THINKING,
            'LOG_LEVEL': self.LOG_LEVEL,
            'LOG_FORMAT': self.LOG_FORMAT,
            'DEBUG_MEMORY': self.DEBUG_MEMORY,
            'DEBUG_LLM': self.DEBUG_LLM,
            'ALLOWED_CHANNEL_IDS': list(self.ALLOWED_CHANNEL_IDS),
            'PERSONALITY': self.PERSONALITY
        }

    def update_from_dict(self, data: dict[str, Any]) -> None:
        """Update config from dictionary"""
        simple_keys = ['DEBUG_MODE', 'TRACE_MESSAGES', 'MAINTENANCE_INTERVAL_HOURS',
                       'ENABLE_VOICE', 'ENABLE_TTS', 'LLM_MODEL', 'VOICE_RECEIVER_MODE',
                       'LLM_BASE_URL', 'LLM_TEMPERATURE', 'LLM_TOP_P',
                       'LLM_MAX_TOKENS', 'LLM_ENABLE_THINKING', 'LOG_LEVEL', 'LOG_FORMAT',
                       'DEBUG_MEMORY', 'DEBUG_LLM']
        for key in simple_keys:
            if key in data:
                if isinstance(getattr(self, key, None), bool):
                    setattr(self, key, bool(data[key]))
                elif isinstance(getattr(self, key, None), int):
                    setattr(self, key, int(data[key]))
                else:
                    setattr(self, key, str(data[key]))

        if 'ALLOWED_CHANNEL_IDS' in data:
            if isinstance(data['ALLOWED_CHANNEL_IDS'], list):
                self.ALLOWED_CHANNEL_IDS = {int(x) for x in data['ALLOWED_CHANNEL_IDS'] if str(x).strip()}

        if 'PERSONALITY' in data:
            self.PERSONALITY.update(data['PERSONALITY'])

        logger.info(" BotConfig updated")

# Global instance
config = BotConfig()
