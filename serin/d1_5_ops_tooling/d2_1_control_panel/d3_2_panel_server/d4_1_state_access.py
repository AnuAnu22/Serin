from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from serin.d1_4_config_base.d2_1_base_config import config


def make_json_safe(obj: Any, _depth: int = 0) -> Any:
    if _depth > 20:
        return str(obj)
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): make_json_safe(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(item, _depth + 1) for item in obj]
    if isinstance(obj, (set, frozenset)):
        return [make_json_safe(item, _depth + 1) for item in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return make_json_safe(vars(obj), _depth + 1)
    return str(obj)


bot_state: dict[str, Any] = {}

active_websockets: list[WebSocket] = []
_ws_lock = asyncio.Lock()

_rate_limit_store: dict[str, list[float]] = {}
_rate_lock = asyncio.Lock()

_request_metrics: dict[str, list[float]] = {}


class ModelConfig(BaseModel):
    model_name: str = Field(..., min_length=1, max_length=256)
    temperature: float = Field(default=0.75, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    make_active: bool = True


class ChannelControl(BaseModel):
    channel_id: str = Field(..., min_length=1, max_length=32, pattern=r"^\d+$")
    action: str = Field(..., pattern=r"^(add|remove)$")


class VoiceChannelControl(BaseModel):
    guild_id: str = Field(..., min_length=1, max_length=32, pattern=r"^\d+$")
    channel_id: str = Field(..., min_length=1, max_length=32, pattern=r"^\d+$")
    action: str = Field(..., pattern=r"^(join|leave)$")


class VoiceLoad(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)


class SettingsUpdate(BaseModel):
    setting_key: str = Field(..., min_length=1, max_length=128)
    setting_value: Any = None


class MemoryQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=64)
    channel_id: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=10, ge=1, le=100)
    memory_type: str | None = Field(
        default=None,
        pattern=r"^(evidence|episode|utterance|summary|bot_response|all)$",
    )
    include_scores: bool = Field(default=True)
    time_decay_days: int = Field(default=60, ge=1, le=365)
    min_importance: float = Field(default=0.0, ge=0.0, le=1.0)


class MemorySearchAdvanced(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None
    channel_id: str | None = None
    limit: int = Field(default=20, ge=1, le=200)
    memory_types: list[str] = Field(default_factory=lambda: ["all"])
    include_bm25_scores: bool = True
    include_vector_scores: bool = True
    include_rrf_scores: bool = True
    include_temporal_scores: bool = True
    time_decay_days: int = Field(default=60, ge=1, le=365)
    min_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    sort_by: str = Field(
        default="rrf",
        pattern=r"^(rrf|vector|bm25|recency|importance)$",
    )


class FactQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    category: str | None = Field(
        default=None,
        pattern=r"^(observation|board_state|game_result|reference|personality|preference)$",
    )
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=10, ge=1, le=50)
    active_only: bool = True


class BeliefQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    state: str | None = Field(
        default=None,
        pattern=r"^(PENDING|SUPPORTED|CONTESTED|SUPERSEDED|UNKNOWN)$",
    )
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=10, ge=1, le=50)


class MoodUpdate(BaseModel):
    energy_level: float | None = Field(default=None, ge=0.0, le=1.0)
    sass_level: float | None = Field(default=None, ge=0.0, le=1.0)
    engagement: float | None = Field(default=None, ge=0.0, le=1.0)
    tone_modifier: str | None = Field(default=None, max_length=200)


app: FastAPI = FastAPI(
    title="Serin Control Panel",
    version="2.0.0",
    description="Production-grade control panel for Serin AI companion",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next: Any) -> Any:
    if config.CONTROL_PANEL_KEY:
        api_key = request.headers.get("X-API-Key", "")
        if api_key != config.CONTROL_PANEL_KEY:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = 60.0
    max_requests = 100

    async with _rate_lock:
        if client_ip not in _rate_limit_store:
            _rate_limit_store[client_ip] = []
        _rate_limit_store[client_ip] = [
            t for t in _rate_limit_store[client_ip] if now - t < window
        ]
        if len(_rate_limit_store[client_ip]) >= max_requests:
            return JSONResponse(
                {"error": "rate_limit_exceeded", "retry_after": int(window)},
                status_code=429,
            )
        _rate_limit_store[client_ip].append(now)

    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start

    path = request.url.path
    if path not in _request_metrics:
        _request_metrics[path] = []
    _request_metrics[path].append(elapsed)
    if len(_request_metrics[path]) > 100:
        _request_metrics[path] = _request_metrics[path][-50:]

    response.headers["X-Response-Time"] = f"{elapsed * 1000:.1f}ms"
    return response


app.mount("/static", StaticFiles(directory="control_panel/static"), name="static")


def get_component(key: str) -> Any | None:
    return bot_state.get(key)


async def get_gpu_vram_usage() -> float:
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
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
            raw = [ln.strip() for ln in stdout.decode().strip().split("\n") if ln.strip()]
            if raw:
                return round(sum(int(ln) for ln in raw if ln.isdigit()) / 1024, 1)
        return 0.0
    except Exception:
        return 0.0


def get_request_metrics() -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for path, times in _request_metrics.items():
        if times:
            metrics[path] = {
                "count": len(times),
                "avg_ms": round(sum(times) / len(times) * 1000, 2),
                "max_ms": round(max(times) * 1000, 2),
                "p95_ms": round(
                    sorted(times)[int(len(times) * 0.95)] * 1000, 2
                ) if len(times) > 1 else round(times[0] * 1000, 2),
            }
    return metrics
