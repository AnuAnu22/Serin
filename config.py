from __future__ import annotations

import os
from typing import Dict, Any, List, Optional, Set
from dotenv import load_dotenv
from logger_config import logger

# Load environment variables
load_dotenv()

class BotConfig:
    _instance: Optional[BotConfig] = None

    def __new__(cls) -> BotConfig:
        if cls._instance is None:
            cls._instance = super(BotConfig, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._initialized: bool = True
        
        # --- Core Settings ---
        self.DISCORD_TOKEN: Optional[str] = os.getenv('DISCORD_TOKEN')
        self.DEBUG_MODE: bool = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        self.TRACE_MESSAGES: bool = os.getenv('TRACE_MESSAGES', 'true').lower() == 'true'
        self.MAINTENANCE_INTERVAL_HOURS: int = int(os.getenv('MAINTENANCE_INTERVAL_HOURS', '24'))
        self.CONTROL_PANEL_PORT: int = int(os.getenv('CONTROL_PANEL_PORT', '8081'))
        
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
        
        # --- Model Settings ---
        self.LLM_MODEL: str = os.getenv('LLM_MODEL', 'solidrust/Hermes-3-Llama-3.1-8B-AWQ')
        self.LLM_API_URL: str = os.getenv('LLM_API_URL', 'http://localhost:30000/v1')
        
        # --- Allowed Channels ---
        allowed_ids_str: str = os.getenv('ALLOWED_CHANNEL_IDS', '')
        self.ALLOWED_CHANNEL_IDS: Set[int] = set()
        if allowed_ids_str:
            try:
                self.ALLOWED_CHANNEL_IDS = {int(x.strip()) for x in allowed_ids_str.split(',') if x.strip()}
            except ValueError:
                logger.warning("⚠️ Invalid ALLOWED_CHANNEL_IDS in .env")
        
        # --- Personality Settings (Runtime only for now) ---
        self.PERSONALITY: Dict[str, float] = {
            'energy': 0.5,
            'sass': 0.5,
            'engagement': 0.5
        }
        
        logger.info("✅ BotConfig initialized")

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for API"""
        return {
            'DEBUG_MODE': self.DEBUG_MODE,
            'TRACE_MESSAGES': self.TRACE_MESSAGES,
            'MAINTENANCE_INTERVAL_HOURS': self.MAINTENANCE_INTERVAL_HOURS,
            'ENABLE_VOICE': self.ENABLE_VOICE,
            'ENABLE_TTS': self.ENABLE_TTS,
            'VOICE_RECEIVER_MODE': self.VOICE_RECEIVER_MODE,
            'LLM_MODEL': self.LLM_MODEL,
            'ALLOWED_CHANNEL_IDS': list(self.ALLOWED_CHANNEL_IDS),
            'PERSONALITY': self.PERSONALITY
        }

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update config from dictionary"""
        simple_keys = ['DEBUG_MODE', 'TRACE_MESSAGES', 'MAINTENANCE_INTERVAL_HOURS',
                       'ENABLE_VOICE', 'ENABLE_TTS', 'LLM_MODEL', 'VOICE_RECEIVER_MODE']
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

        logger.info("⚙️ BotConfig updated")

# Global instance
config = BotConfig()
