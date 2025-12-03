import os
from typing import Dict, Any, List
from dotenv import load_dotenv
from logger_config import logger

# Load environment variables
load_dotenv()

class BotConfig:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BotConfig, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # --- Core Settings ---
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        self.TRACE_MESSAGES = os.getenv('TRACE_MESSAGES', 'true').lower() == 'true'
        self.MAINTENANCE_INTERVAL_HOURS = int(os.getenv('MAINTENANCE_INTERVAL_HOURS', '24'))
        self.CONTROL_PANEL_PORT = int(os.getenv('CONTROL_PANEL_PORT', '8080'))
        
        # --- Feature Flags ---
        self.ENABLE_VOICE = os.getenv('ENABLE_VOICE', 'true').lower() == 'true'
        self.ENABLE_TTS = os.getenv('ENABLE_TTS', 'true').lower() == 'true'
        
        # --- Qdrant Settings ---
        self.QDRANT_HOST = os.getenv('QDRANT_HOST', 'localhost')
        self.QDRANT_PORT = int(os.getenv('QDRANT_PORT', '6333'))
        
        # --- Model Settings ---
        self.LLM_MODEL = os.getenv('LLM_MODEL', 'solidrust/Hermes-3-Llama-3.1-8B-AWQ')
        self.LLM_API_URL = os.getenv('LLM_API_URL', 'http://localhost:30000/v1')
        
        # --- Allowed Channels ---
        allowed_ids_str = os.getenv('ALLOWED_CHANNEL_IDS', '')
        self.ALLOWED_CHANNEL_IDS = set()
        if allowed_ids_str:
            try:
                self.ALLOWED_CHANNEL_IDS = {int(x.strip()) for x in allowed_ids_str.split(',') if x.strip()}
            except ValueError:
                logger.warning("⚠️ Invalid ALLOWED_CHANNEL_IDS in .env")
        
        # --- Personality Settings (Runtime only for now) ---
        self.PERSONALITY = {
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
            'LLM_MODEL': self.LLM_MODEL,
            'ALLOWED_CHANNEL_IDS': list(self.ALLOWED_CHANNEL_IDS),
            'PERSONALITY': self.PERSONALITY
        }

    def update_from_dict(self, data: Dict[str, Any]):
        """Update config from dictionary"""
        if 'DEBUG_MODE' in data:
            self.DEBUG_MODE = bool(data['DEBUG_MODE'])
        if 'TRACE_MESSAGES' in data:
            self.TRACE_MESSAGES = bool(data['TRACE_MESSAGES'])
        if 'MAINTENANCE_INTERVAL_HOURS' in data:
            self.MAINTENANCE_INTERVAL_HOURS = int(data['MAINTENANCE_INTERVAL_HOURS'])
        if 'ENABLE_VOICE' in data:
            self.ENABLE_VOICE = bool(data['ENABLE_VOICE'])
        if 'ENABLE_TTS' in data:
            self.ENABLE_TTS = bool(data['ENABLE_TTS'])
        if 'PERSONALITY' in data:
            self.PERSONALITY.update(data['PERSONALITY'])
            
        logger.info("⚙️ BotConfig updated")

# Global instance
config = BotConfig()
