"""
Web Server - Control Panel for Serin Bot
FastAPI-based web interface for complete bot control.

Features:
- Model control (start/stop/switch)
- Voice control (join/leave VC, transcription toggle)
- Settings management
- Real-time logs via WebSocket
- Memory browser
- Stats dashboard
"""
import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from serin.config.logger import logger
from serin.ops.control_panel.routes import register_enhanced_routes
from serin.config.config import config

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
bot_state = {
    'discord_client': None,
    'message_manager': None,
    'background_processor': None,
    'passive_monitor': None,
    'message_crawler': None,
    'memory_system': None,
    'voice_listener': None,  # TIER 6
    'tts_engine': None,       # TIER 7
    'voice_manager': None,    # TIER 8
    'voice_behavior_manager': None,  # TIER 9
    'bot_stats': {}
}

# WebSocket connections for live updates
active_websockets = []


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
    user_id: Optional[str] = None
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
async def check_auth(request: Request, call_next) -> Any:
    if config.CONTROL_PANEL_KEY:
        api_key = request.headers.get("X-API-Key", "")
        if api_key != config.CONTROL_PANEL_KEY:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)

# Mount static files
app.mount("/static", StaticFiles(directory="control_panel/static"), name="static")


# ============================================================================
# WEBSOCKET - REAL-TIME UPDATES
# ============================================================================
# Replace WebSocket endpoint in web_server.py

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> Any:
    """WebSocket for real-time log streaming and stats updates"""
    await websocket.accept()
    active_websockets.append(websocket)
    logger.info(f" WebSocket connected (total: {len(active_websockets)})")
    
    try:
        # Send initial stats immediately
        try:
            client = bot_state['discord_client']
            latency = int(client.latency * 1000) if client else 0
            manager = bot_state['message_manager']
            brain_state = 'ONLINE'
            if manager and hasattr(manager, 'current_state'):
                brain_state = manager.current_state.get('status', 'ONLINE')
            gpu = get_gpu_vram_usage()

            await websocket.send_json({
                "type": "heartbeat",
                "latency": latency,
                "gpu": gpu,
                "brain_state": brain_state
            })
        except Exception as e:
            logger.error(f"Error sending initial stats: {e}")
            raise

        while True:
            # Wait for messages or timeout
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

            if not websocket.client_state.value == 1:
                break

            # Send Heartbeat
            try:
                client = bot_state['discord_client']
                latency = int(client.latency * 1000) if client else 0
                manager = bot_state['message_manager']
                brain_state = 'ONLINE'
                if manager and hasattr(manager, 'current_state'):
                    brain_state = manager.current_state.get('status', 'ONLINE')
                gpu = get_gpu_vram_usage()

                await websocket.send_json({
                    "type": "heartbeat",
                    "latency": latency,
                    "gpu": gpu,
                    "brain_state": brain_state
                })

            except Exception as e:
                logger.debug(f"Error sending heartbeat: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"WebSocket disconnected (remaining: {len(active_websockets)})")

def get_gpu_vram_usage() -> float:
    """Get GPU VRAM usage in GB via nvidia-smi"""
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
            if lines:
                total_mb = sum(int(l) for l in lines if l.isdigit())
                return round(total_mb / 1024, 1)
        return 0.0
    except Exception:
        return 0.0

async def broadcast_log(log_entry: Dict[str, Any]) -> None:
    """Broadcast log entry to all connected WebSockets"""
    to_remove = []
    
    for ws in active_websockets:
        try:
            # Check if connection is still open
            if ws.client_state.value != 1:
                to_remove.append(ws)
                continue
                
            await ws.send_json({
                'type': 'log',
                'msg': log_entry.get('message', str(log_entry))
            })
        except Exception:
            to_remove.append(ws)
    
    # Remove disconnected
    for ws in to_remove:
        if ws in active_websockets:
            active_websockets.remove(ws)


async def broadcast_event(event_type: str, data: Dict[str, Any]) -> None:
    """Broadcast event to all connected WebSockets"""
    to_remove = []
    
    for ws in active_websockets:
        try:
            # Check if connection is still open
            if ws.client_state.value != 1:
                to_remove.append(ws)
                continue
                
            # Pass through decision events directly
            if event_type == 'decision':
                 await ws.send_json(data)
            else:
                await ws.send_json({
                    'type': event_type,
                    'data': data
                })
        except Exception:
            to_remove.append(ws)
    
    for ws in to_remove:
        if ws in active_websockets:
            active_websockets.remove(ws)

register_enhanced_routes(app, bot_state, broadcast_event )
# ============================================================================
# HOMEPAGE
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def homepage() -> Any:
    """Serve main dashboard"""
    return FileResponse("control_panel/static/index.html")


# ============================================================================
# BOT STATUS
# ============================================================================

@app.get("/api/status")
async def get_status() -> Any:
    """Get current bot status"""
    client = bot_state['discord_client']
    
    if not client:
        return {
            'online': False,
            'user': None,
            'guilds': [],
            'latency': 0
        }
    
    guilds = []
    if client.guilds:
        for guild in client.guilds:
            guilds.append({
                'id': str(guild.id),
                'name': guild.name,
                'member_count': guild.member_count,
                'text_channels': len(guild.text_channels),
                'voice_channels': len(guild.voice_channels)
            })
    
    return {
        'online': client.is_ready(),
        'user': {
            'id': str(client.user.id),
            'name': client.user.name,
            'discriminator': client.user.discriminator
        } if client.user else None,
        'guilds': guilds,
        'latency': round(client.latency * 1000, 2)  # ms
    }


@app.get("/api/stats")
async def get_stats() -> Any:
    """Get comprehensive bot statistics"""
    return get_current_stats()

@app.get("/api/health")
async def get_system_health() -> Any:
    """Get health status of all components"""
    health = {
        'status': 'healthy',
        'components': {}
    }
    
    # 1. Discord
    client = bot_state['discord_client']
    health['components']['discord'] = {
        'status': 'ok' if client and client.is_ready() else 'error',
        'latency': round(client.latency * 1000, 2) if client else 0
    }
    
    # 2. Memory
    mem = bot_state['memory_system']
    health['components']['memory'] = {
        'status': 'ok' if mem else 'error',
        'type': 'Qdrant' if mem and hasattr(mem, 'qdrant_client') else 'Unknown'
    }
    
    # 3. Voice Input
    listener = bot_state['voice_listener']
    health['components']['voice_input'] = {
        'status': 'ok' if listener else 'disabled',
        'connected': listener.is_connected() if listener else False
    }
    
    # 4. TTS
    tts = bot_state['tts_engine']
    health['components']['tts'] = {
        'status': 'ok' if tts and tts.tts else 'disabled',
        'model': tts.model_name if tts else None
    }
    
    # 5. Background Processor
    bg = bot_state['background_processor']
    health['components']['background'] = {
        'status': 'ok' if bg and bg.is_running else 'stopped',
        'queue_size': len(bg.processing_queue) if bg else 0
    }
    
    return health

def get_current_stats() -> Dict[str, Any]:
    """Helper to get current stats from all systems (JSON-safe)"""
    stats = {}
    
    # Message Manager stats
    try:
        if bot_state['message_manager']:
            stats['manager'] = bot_state['message_manager'].stats.copy()
    except Exception as e:
        logger.error(f"Error getting manager stats: {e}")
        stats['manager'] = {}
    
    # Background Processor stats
    try:
        if bot_state['background_processor']:
            bg_stats = bot_state['background_processor'].get_stats()
            stats['background'] = bg_stats
    except Exception as e:
        logger.error(f"Error getting bg stats: {e}")
        stats['background'] = {}
    
    # Passive Monitor stats
    try:
        if bot_state['passive_monitor']:
            passive_stats = bot_state['passive_monitor'].get_stats()
            stats['passive'] = passive_stats
    except Exception as e:
        logger.error(f"Error getting passive stats: {e}")
        stats['passive'] = {}
    
    # Message Crawler stats
    try:
        if bot_state['message_crawler']:
            crawler_stats = bot_state['message_crawler'].get_stats()
            stats['crawler'] = crawler_stats
    except Exception as e:
        logger.error(f"Error getting crawler stats: {e}")
        stats['crawler'] = {}
    
    # Memory System stats
    try:
        if bot_state['memory_system']:
            mem_stats = bot_state['memory_system'].get_stats()
            stats['memory'] = mem_stats
    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        stats['memory'] = {}
    
    # Voice Listener stats
    try:
        if bot_state['voice_listener']:
            voice_stats = bot_state['voice_listener'].get_stats()
            stats['voice'] = voice_stats
    except Exception as e:
        logger.error(f"Error getting voice stats: {e}")
        stats['voice'] = {}
    
    # Bot-level stats
    stats['bot'] = bot_state.get('bot_stats', {})
    
    # Make everything JSON-safe
    return make_json_safe(stats)
# ============================================================================
# MODEL INFO (vLLM)
# ============================================================================

@app.get("/api/model")
async def get_model_info() -> Any:
    """Return active vLLM model info"""
    try:
        from serin.state.model_system.factory import get_model_connector
        connector = get_model_connector()
        # Lazy load to ensure info is available
        if getattr(connector, 'client', None) is None:
            connector.load_model()
        return connector.get_model_info()
    except Exception as e:
        logger.error(f" Error getting model info: {e}")
        return {'error': str(e)}


# ============================================================================
# BACKGROUND PROCESSOR CONTROL
# ============================================================================

@app.post("/api/background/start")
async def start_background_processor() -> Any:
    """Start background processor"""
    try:
        bg = bot_state['background_processor']
        if bg:
            await bg.start()
            return {'success': True}
        return {'success': False, 'error': 'Background processor not initialized'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.post("/api/background/stop")
async def stop_background_processor() -> Any:
    """Stop background processor"""
    try:
        bg = bot_state['background_processor']
        if bg:
            await bg.stop()
            return {'success': True}
        return {'success': False, 'error': 'Background processor not initialized'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# CHANNEL CONTROL
# ============================================================================

@app.get("/api/channels/allowed")
async def get_allowed_channels() -> Any:
    """Get list of allowed channels"""
    try:
        import discord_bot
        return {
            'channels': [str(cid) for cid in discord_bot.ALLOWED_CHANNEL_IDS]
        }
    except Exception as e:
        return {'error': str(e)}
