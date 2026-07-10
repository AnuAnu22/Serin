"""Shared control-panel state: FastAPI app, globals, models, and helpers.

Extracted from the former ``server.py`` so the route submodules
(``websocket``, ``status``, ``controls``) can import these without creating a
circular import with the package ``__init__``. Nothing in this module imports
from the rest of the ``server`` package.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from serin.d1_4_config_base.config import config


def make_json_safe(obj: Any) -> Any:
    """
    Recursively convert non-JSON-serializable objects to safe types.
    Handles: set, datetime, custom objects
    """
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, set):
        return list(obj)  # Convert set to list
    elif hasattr(obj, 'isoformat'):  # datetime
        return obj.isoformat()
    elif hasattr(obj, '__dict__'):  # Custom objects
        return make_json_safe(obj.__dict__)
    else:
        return obj


# ============================================================================
# GLOBAL STATE (will be injected by main bot)
# ============================================================================
bot_state: dict[str, Any] = {}

# WebSocket connections for live updates
active_websockets: list[WebSocket] = []


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ModelConfig(BaseModel):
    model_name: str
    temperature: float = 0.75
    top_p: float = 0.9
    make_active: bool = True  # Whether to make this the active model after loading


class ChannelControl(BaseModel):
    channel_id: str
    action: str  # 'add' or 'remove'


class VoiceChannelControl(BaseModel):
    guild_id: str
    channel_id: str
    action: str  # 'join' or 'leave'


class VoiceLoad(BaseModel):
    filename: str


class SettingsUpdate(BaseModel):
    setting_key: str
    setting_value: Any


class MemoryQuery(BaseModel):
    query: str
    user_id: str | None = None
    limit: int = 10


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="Serin Control Panel", version="1.0.0")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware
@app.middleware("http")
async def check_auth(request: Request, call_next: Any) -> Any:
    if config.CONTROL_PANEL_KEY:
        api_key = request.headers.get("X-API-Key", "")
        if api_key != config.CONTROL_PANEL_KEY:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)

# Mount static files
app.mount("/static", StaticFiles(directory="control_panel/static"), name="static")


async def get_gpu_vram_usage() -> float:
    """Get GPU VRAM usage in GB via nvidia-smi"""
    try:
        proc = await asyncio.create_subprocess_exec(
            'nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return 0.0
        if proc.returncode == 0:
            output = stdout.decode()
            raw_lines = [line.strip() for line in output.strip().split('\n') if line.strip()]
            if raw_lines:
                total_mb = sum(int(line) for line in raw_lines if line.isdigit())
                return round(total_mb / 1024, 1)
        return 0.0
    except Exception:
        return 0.0
