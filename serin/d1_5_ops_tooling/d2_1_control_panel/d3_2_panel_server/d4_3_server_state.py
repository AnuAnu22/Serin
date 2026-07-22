"""Shared control-panel state: FastAPI app, globals, models, and helpers.

Extracted from the former ``server.py`` so the route submodules
(``websocket``, ``status``, ``controls``) can import these without creating a
circular import with the package ``__init__``. Nothing in this module imports
from the rest of the ``server`` package.
"""

from __future__ import annotations

import asyncio
import hmac
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from serin.d1_4_config_base.d2_1_base_config import config


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

# WebSocket connections for live updates. Mutated from three different
# coroutines that can interleave arbitrarily on the event loop: a new
# connection's accept handler (append), a disconnecting client's cleanup
# (remove), and every broadcast_log/broadcast_event call (iterate + remove
# dead entries). A plain list under concurrent mutation-while-iterating can
# skip entries, double-remove, or raise — `active_websockets_lock` serializes
# all access. It's an asyncio.Lock, not threading.Lock, because everything
# here runs on the same event loop; there is no cross-thread contention to
# guard against, just interleaved coroutines.
active_websockets: list[WebSocket] = []
active_websockets_lock = asyncio.Lock()


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

# CORS: origins come from CONTROL_PANEL_ALLOWED_ORIGINS (comma-separated),
# defaulting to same-origin only. "*" + allow_credentials=True is a real
# vulnerability — it lets any website the operator's browser visits make
# authenticated requests to the panel on their behalf (CSRF-by-CORS). Never
# widen this back to "*" while allow_credentials stays True.
_cors_origins = [o.strip() for o in config.CONTROL_PANEL_ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type"],
)


def _key_is_valid(provided: str) -> bool:
    """Constant-time comparison — plain ``!=`` leaks timing info that lets an
    attacker recover the key byte-by-byte over enough requests."""
    return hmac.compare_digest(provided, config.CONTROL_PANEL_KEY)


# Auth middleware. Applies to every route including WebSocket upgrade
# requests and the static file mount below — there is no "public" surface
# on this app once a key is configured.
@app.middleware("http")
async def check_auth(request: Request, call_next: Any) -> Any:
    if config.CONTROL_PANEL_KEY:
        api_key = request.headers.get("X-API-Key", "")
        if not _key_is_valid(api_key):
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
