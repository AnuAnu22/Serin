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
from serin.core.logger import logger
from serin.core.config import config
from enhanced_api_routes import register_enhanced_routes

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
async def check_auth(request: Request, call_next):
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
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time log streaming and stats updates"""
    await websocket.accept()
    active_websockets.append(websocket)
    logger.info(f"🌐 WebSocket connected (total: {len(active_websockets)})")
    
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
async def homepage():
    """Serve main dashboard"""
    return FileResponse("control_panel/static/index.html")


# ============================================================================
# BOT STATUS
# ============================================================================

@app.get("/api/status")
async def get_status():
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
async def get_stats():
    """Get comprehensive bot statistics"""
    return get_current_stats()

@app.get("/api/health")
async def get_system_health():
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
async def get_model_info():
    """Return active vLLM model info"""
    try:
        from models.model_factory import get_model_connector
        connector = get_model_connector()
        # Lazy load to ensure info is available
        if getattr(connector, 'client', None) is None:
            connector.load_model()
        return connector.get_model_info()
    except Exception as e:
        logger.error(f"❌ Error getting model info: {e}")
        return {'error': str(e)}


# ============================================================================
# BACKGROUND PROCESSOR CONTROL
# ============================================================================

@app.post("/api/background/start")
async def start_background_processor():
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
async def stop_background_processor():
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
async def get_allowed_channels():
    """Get list of allowed channels"""
    try:
        import discord_bot
        return {
            'channels': [str(cid) for cid in discord_bot.ALLOWED_CHANNEL_IDS]
        }
    except Exception as e:
        return {'error': str(e)}


@app.post("/api/channels/allowed")
async def update_allowed_channels(control: ChannelControl):
    """Add or remove allowed channel"""
    try:
        import discord_bot
        channel_id = int(control.channel_id)
        
        if control.action == 'add':
            discord_bot.ALLOWED_CHANNEL_IDS.add(channel_id)
        elif control.action == 'remove':
            discord_bot.ALLOWED_CHANNEL_IDS.discard(channel_id)
        else:
            return {'success': False, 'error': 'Invalid action'}
        
        logger.info(f"📋 Channel {control.action}: {channel_id}")
        return {
            'success': True,
            'channels': [str(cid) for cid in discord_bot.ALLOWED_CHANNEL_IDS]
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# VOICE CONTROL (TIER 6)
# ============================================================================

@app.get("/api/voice/channels")
async def get_voice_channels():
    """Get all voice channels across servers"""
    try:
        client = bot_state['discord_client']
        if not client:
            return {'channels': []}
        
        channels = []
        for guild in client.guilds:
            for vc in guild.voice_channels:
                channels.append({
                    'guild_id': str(guild.id),
                    'guild_name': guild.name,
                    'channel_id': str(vc.id),
                    'channel_name': vc.name,
                    'members': len(vc.members),
                    'connected': False  # Will update when voice listener implemented
                })
        
        return {'channels': channels}
    except Exception as e:
        return {'error': str(e)}


@app.post("/api/voice/join")
async def join_voice_channel(control: VoiceChannelControl):
    """Join a voice channel"""
    try:
        voice_listener = bot_state['voice_listener']
        if not voice_listener:
            return {'success': False, 'error': 'Voice listener not initialized'}
        
        success = await voice_listener.join_channel(
            int(control.guild_id),
            int(control.channel_id)
        )
        
        if success:
            logger.info(f"🎤 Joined voice channel: {control.channel_id}")
            await broadcast_event('voice_joined', {
                'guild_id': control.guild_id,
                'channel_id': control.channel_id
            })
        
        return {'success': success}
    except Exception as e:
        logger.error(f"Error joining voice: {e}")
        return {'success': False, 'error': str(e)}


@app.post("/api/voice/leave")
async def leave_voice_channel(control: VoiceChannelControl):
    """Leave a voice channel"""
    try:
        voice_listener = bot_state['voice_listener']
        if not voice_listener:
            return {'success': False, 'error': 'Voice listener not initialized'}
        
        success = await voice_listener.leave_channel(int(control.guild_id))
        
        if success:
            logger.info(f"🎤 Left voice channel in guild: {control.guild_id}")
            await broadcast_event('voice_left', {
                'guild_id': control.guild_id
            })
        
        return {'success': success}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.get("/api/voice/status")
async def get_voice_status():
    """Get current voice connection status"""
    try:
        voice_listener = bot_state['voice_listener']
        if not voice_listener:
            return {'connected': False}
        
        return voice_listener.get_status()
    except Exception as e:
        return {'error': str(e)}

# --- VOICE CLONING (TIER 8) ---

@app.get("/api/voice/files")
async def list_voice_files():
    """List available voice files"""
    try:
        manager = bot_state['voice_manager']
        if not manager:
            return {'voices': []}
        
        return {'voices': manager.list_voices()}
    except Exception as e:
        return {'error': str(e)}

@app.post("/api/voice/load")
async def load_voice_file(data: VoiceLoad):
    """Load a voice file for cloning"""
    try:
        manager = bot_state['voice_manager']
        tts = bot_state['tts_engine']
        
        if not manager or not tts:
            return {'success': False, 'error': 'Voice system not initialized'}
        
        success = manager.load_voice(tts, data.filename)
        return {'success': success}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.post("/api/voice/clear")
async def clear_voice_file():
    """Clear voice cloning (revert to default)"""
    try:
        manager = bot_state['voice_manager']
        tts = bot_state['tts_engine']
        
        if not manager or not tts:
            return {'success': False, 'error': 'Voice system not initialized'}
        
        success = manager.clear_voice(tts)
        return {'success': success}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# MEMORY BROWSER
# ============================================================================

@app.post("/api/memory/search")
async def search_memories(query: MemoryQuery):
    """Search memories"""
    try:
        memory = bot_state['memory_system']
        if not memory:
            return {'memories': []}
        
        results = memory.search_memories(
            query=query.query,
            user_id=query.user_id,
            n_results=query.limit
        )
        
        return {'memories': results}
    except Exception as e:
        return {'error': str(e)}


@app.get("/api/memory/users")
async def get_all_users():
    """Get all users in memory"""
    try:
        memory = bot_state['memory_system']
        if not memory:
            return {'users': []}
        
        cursor = memory.conn.cursor()
        cursor.execute("SELECT user_id, username, total_messages FROM users ORDER BY total_messages DESC LIMIT 100")
        
        users = [dict(row) for row in cursor.fetchall()]
        return {'users': users}
    except Exception as e:
        return {'error': str(e)}


@app.get("/api/memory/user/{user_id}")
async def get_user_profile(user_id: str):
    """Get detailed user profile"""
    try:
        memory = bot_state['memory_system']
        if not memory:
            return {'error': 'Memory not initialized'}
        
        profile = memory.get_user_profile(user_id)
        if profile:
            return profile
        else:
            return {'error': 'User not found'}
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# SETTINGS
# ============================================================================

# ============================================================================
# BRAIN CONTROL (TIER 8)
# ============================================================================

@app.get("/api/brain/state")
async def get_brain_state():
    """Get current brain state (thinking, generating, etc.)"""
    try:
        manager = bot_state['message_manager']
        if not manager:
            return {'status': 'OFFLINE'}
        
        return manager.current_state
    except Exception as e:
        return {'error': str(e)}

@app.post("/api/brain/abort")
async def abort_generation():
    """Abort current generation"""
    try:
        manager = bot_state['message_manager']
        if not manager:
            return {'success': False, 'error': 'Manager not initialized'}
        
        manager.abort_current_generation()
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.post("/api/emergency-stop")
async def emergency_stop():
    """Emergency stop alias"""
    return await abort_generation()

@app.post("/api/bot/restart")
async def restart_bot():
    """Restart the bot process (hot-reloads code changes). The hot_reloader.py wrapper will auto-restart."""
    try:
        import os
        open("/tmp/serin-restart.signal", "w").close()
        logger.warning("🔄 Restart signal sent to hot-reloader")
        return {'success': True, 'message': 'Restart signal sent'}
    except Exception as e:
        logger.error(f"Failed to send restart signal: {e}")
        return {'success': False, 'error': str(e)}

class MoodRequest(BaseModel):
    mood: str

@app.post("/api/mood/set")
async def set_mood(request: MoodRequest):
    """Set bot mood"""
    try:
        manager = bot_state['message_manager']
        if not manager:
            return {'success': False, 'error': 'Manager not initialized'}
        
        # Access personality state directly
        if hasattr(manager, 'personality'):
            if request.mood == 'high_energy':
                manager.personality.energy_level = 1.0
                manager.personality.engagement = 1.0
            elif request.mood == 'neutral':
                manager.personality.energy_level = 0.5
                manager.personality.sass_level = 0.5
            elif request.mood == 'sass':
                manager.personality.sass_level = 1.0
            
            return {'success': True, 'mood': request.mood}
            
        return {'success': False, 'error': 'Personality module not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

class ContextSeverRequest(BaseModel):
    channel_id: str

@app.post("/api/context/sever")
async def sever_context(request: ContextSeverRequest):
    """Sever proactive context for a channel"""
    try:
        manager = bot_state['message_manager']
        if not manager or not hasattr(manager, 'response_controller'):
             return {'success': False, 'error': 'Manager not initialized'}
             
        rc = manager.response_controller
        if request.channel_id in rc.active_conversations:
            del rc.active_conversations[request.channel_id]
            logger.info(f"✂️ Severed context for {request.channel_id}")
            return {'success': True}
            
        return {'success': False, 'error': 'Context not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.get("/api/system_prompt")
async def get_system_prompt():
    """Get current system prompt"""
    try:
        manager = bot_state['message_manager']
        if not manager:
            return {'prompt': ''}
        
        return {'prompt': manager.system_prompt}
    except Exception as e:
        return {'error': str(e)}

@app.post("/api/system_prompt")
async def update_system_prompt(data: Dict[str, str]):
    """Update system prompt"""
    try:
        manager = bot_state['message_manager']
        if not manager:
            return {'success': False, 'error': 'Manager not initialized'}
        
        new_prompt = data.get('prompt')
        if new_prompt:
            manager.system_prompt = new_prompt
            # Ideally persist this to disk too
            return {'success': True}
        return {'success': False, 'error': 'No prompt provided'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ============================================================================
# CONFIGURATION (TIER 8)
# ============================================================================

@app.get("/api/config")
async def get_full_config():
    """Get full bot configuration"""
    try:
        return config.to_dict()
    except Exception as e:
        return {'error': str(e)}

@app.post("/api/config")
async def update_full_config(data: Dict[str, Any]):
    """Update bot configuration"""
    try:
        config.update_from_dict(data)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ============================================================================
# SETTINGS (Legacy - Redirect to Config)
# ============================================================================

@app.get("/api/settings")
async def get_settings():
    """Get all configurable settings (Legacy)"""
    return await get_full_config()

@app.post("/api/settings/update")
async def update_setting(update: SettingsUpdate):
    """Update a setting (Legacy wrapper)"""
    try:
        from serin.core.config import config
        # Map legacy keys to config keys
        key_map = {
            'debug_mode': 'DEBUG_MODE',
            'trace_messages': 'TRACE_MESSAGES',
            'maintenance_interval': 'MAINTENANCE_INTERVAL_HOURS'
        }
        
        if update.setting_key in key_map:
            config.update_from_dict({key_map[update.setting_key]: update.setting_value})
            return {'success': True}
        
        return {'success': False, 'error': 'Unknown setting key'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# LOGS
# ============================================================================

@app.get("/api/logs/recent")
async def get_recent_logs():
    """Get recent log entries"""
    try:
        # Read last 100 lines from log file
        log_file = "bot.log"
        if not os.path.exists(log_file):
            return {'logs': []}
        
        with open(log_file, 'r') as f:
            lines = f.readlines()[-100:]
        
        return {'logs': lines}
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# CRAWLER CONTROL
# ============================================================================

@app.post("/api/crawler/trigger-sync")
async def trigger_manual_sync():
    """Manually trigger a quick sync"""
    try:
        crawler = bot_state['message_crawler']
        if not crawler:
            return {'success': False, 'error': 'Crawler not initialized'}
        
        # Trigger sync in background
        asyncio.create_task(_run_manual_sync(crawler))
        
        return {'success': True, 'message': 'Sync started'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def _run_manual_sync(crawler):
    """Background task for manual sync"""
    try:
        logger.info("🔄 Manual sync triggered from control panel")
        client = bot_state['discord_client']
        
        synced_count = 0
        for guild in client.guilds:
            for channel in guild.text_channels:
                try:
                    synced = await crawler._quick_sync_channel(channel)
                    synced_count += synced
                except:
                    pass
        
        logger.info(f"✅ Manual sync complete: {synced_count} messages")
        await broadcast_event('sync_complete', {'count': synced_count})
    except Exception as e:
        logger.error(f"Error in manual sync: {e}")


# ============================================================================
# TTS CONTROL
# ============================================================================

@app.get("/api/tts/voices")
async def list_tts_voices():
    """List available TTS voice files"""
    try:
        # Try voice_manager first (TTSVoiceManager)
        manager = bot_state['voice_manager']
        if manager and hasattr(manager, 'list_voices') and callable(manager.list_voices):
            voices = manager.list_voices()
            if voices:
                return {'voices': voices}
        # Try edge-tts built-in list
        try:
            import edge_tts
            edge_voices = await edge_tts.list_voices()
            return {'voices': [{'name': v['Name'], 'file': v['ShortName'], 'size': 0} for v in edge_voices[:50]]}
        except Exception:
            pass
        return {'voices': []}
    except Exception as e:
        return {'error': str(e)}

@app.get("/api/tts/current")
async def get_current_tts():
    """Get current TTS engine status"""
    try:
        tts = bot_state['tts_engine']
        if not tts:
            return {'error': 'TTS not initialized'}
        status = {
            'device': 'cuda' if hasattr(tts, 'device') and tts.device else 'cpu',
            'cuda_enabled': hasattr(tts, 'device') and tts.device and 'cuda' in str(tts.device),
            'voice_cloning_active': getattr(tts, 'voice_cloning_active', False),
            'total_generations': getattr(tts, 'total_generations', 0),
            'active_profile': getattr(tts, 'active_profile', 'default'),
            'available_profiles': getattr(tts, 'available_profiles', ['default']),
        }
        return make_json_safe(status)
    except Exception as e:
        return {'error': str(e)}

@app.post("/api/tts/voice/load")
async def load_tts_voice(data: Dict[str, Any]):
    """Load a TTS voice file"""
    try:
        tts = bot_state['tts_engine']
        if not tts:
            return {'success': False, 'error': 'TTS not initialized'}
        voice_name = data.get('voice_name', '')
        if hasattr(tts, 'load_voice'):
            success = await tts.load_voice(voice_name)
            return {'success': success, 'voice': voice_name}
        return {'success': False, 'error': 'load_voice not available'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.post("/api/tts/voice/clear")
async def clear_tts_voice():
    """Clear custom TTS voice, revert to default"""
    try:
        tts = bot_state['tts_engine']
        if not tts:
            return {'success': False, 'error': 'TTS not initialized'}
        if hasattr(tts, 'clear_voice'):
            await tts.clear_voice()
            return {'success': True}
        return {'success': False, 'error': 'clear_voice not available'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.post("/api/tts/settings/update")
async def update_tts_settings(data: Dict[str, Any]):
    """Update TTS settings (profile, speed, etc.)"""
    try:
        tts = bot_state['tts_engine']
        if not tts:
            return {'success': False, 'error': 'TTS not initialized'}
        profile = data.get('profile')
        if profile and hasattr(tts, 'set_active_profile'):
            tts.set_active_profile(profile)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ============================================================================
# AUDIO PROCESSING SETTINGS
# ============================================================================

@app.get("/api/audio/settings")
async def get_audio_settings():
    """Get audio processing settings"""
    try:
        listener = bot_state['voice_listener']
        if not listener:
            return {'vad_threshold': -40, 'silence_threshold': 3.0, 'transcription_enabled': True}
        ap = getattr(listener, 'audio_processor', None)
        return {
            'vad_threshold': getattr(ap, 'VAD_THRESHOLD', -40) if ap else -40,
            'silence_threshold': getattr(ap, 'silence_threshold', 3.0) if ap else 3.0,
            'transcription_enabled': listener.transcription_enabled if hasattr(listener, 'transcription_enabled') else True,
        }
    except Exception as e:
        return {'error': str(e)}

@app.post("/api/audio/settings/update")
async def update_audio_settings(data: Dict[str, Any]):
    """Update audio processing settings"""
    try:
        listener = bot_state['voice_listener']
        if not listener:
            return {'success': False, 'error': 'Voice listener not initialized'}
        ap = getattr(listener, 'audio_processor', None)
        if 'vad_threshold' in data and ap:
            ap.VAD_THRESHOLD = int(data['vad_threshold'])
        if 'silence_threshold' in data and ap:
            ap.silence_threshold = float(data['silence_threshold'])
        if 'transcription_enabled' in data:
            listener.transcription_enabled = bool(data['transcription_enabled'])
        logger.info("🎙️ Audio settings updated from web panel")
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.get("/api/audio/stats")
async def get_audio_stats():
    """Get audio processing statistics"""
    try:
        listener = bot_state['voice_listener']
        if not listener:
            return {'chunks_received': 0, 'chunks_processed': 0, 'queue_size': 0, 'transcriptions_completed': 0, 'vad_detections': 0}
        ap = getattr(listener, 'audio_processor', None)
        if ap and hasattr(ap, 'get_stats'):
            return ap.get_stats()
        return {
            'chunks_received': listener.stats.get('total_audio_chunks', 0),
            'chunks_processed': listener.stats.get('total_audio_chunks', 0),
            'queue_size': 0,
            'transcriptions_completed': 0,
            'vad_detections': 0,
        }
    except Exception as e:
        return {'error': str(e)}

@app.get("/api/audio/speakers")
async def get_active_speakers():
    """Get currently active/streaming speakers"""
    try:
        listener = bot_state['voice_listener']
        if not listener:
            return {'speakers': []}
        ap = getattr(listener, 'audio_processor', None)
        if ap and hasattr(ap, 'get_active_speakers'):
            speakers = await ap.get_active_speakers()
            return {'speakers': speakers}
        return {'speakers': []}
    except Exception as e:
        return {'error': str(e)}

# ============================================================================
# VOICE PROFILES
# ============================================================================

@app.get("/api/voice-profiles/list")
async def list_voice_profiles():
    """List all voice profiles"""
    try:
        from voice.voice_profiles import get_voice_profiles, get_active_profile_name
        profiles = get_voice_profiles()
        active = get_active_profile_name()
        return {
            'profiles': [
                {
                    'name': p.name,
                    'speed': getattr(p, 'speed', 1.0),
                    'temperature': getattr(p, 'temperature', 0.7),
                    'description': getattr(p, 'description', ''),
                }
                for p in profiles
            ],
            'active': active,
        }
    except Exception as e:
        return {'error': str(e), 'profiles': [], 'active': 'default'}

@app.post("/api/voice-profiles/create")
async def create_voice_profile(data: Dict[str, Any]):
    """Create a new voice profile"""
    try:
        from voice.voice_profiles import create_profile
        name = data.get('name')
        if not name:
            return {'success': False, 'error': 'Profile name required'}
        profile = create_profile(
            name=name,
            speed=data.get('speed', 1.0),
            temperature=data.get('temperature', 0.7),
            description=data.get('description', ''),
        )
        if profile:
            logger.info("📋 Voice profile created: %s", name)
            return {'success': True}
        return {'success': False, 'error': 'Failed to create profile'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.post("/api/voice-profiles/set-active")
async def set_active_voice_profile(profile_name: str = 'default'):
    """Set active voice profile"""
    try:
        from voice.voice_profiles import set_active_profile
        success = set_active_profile(profile_name)
        if success:
            logger.info("🎙️ Active voice profile: %s", profile_name)
            return {'success': True}
        return {'success': False, 'error': 'Profile not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.delete("/api/voice-profiles/{profile_name}")
async def delete_voice_profile(profile_name: str):
    """Delete a voice profile"""
    try:
        from voice.voice_profiles import delete_profile
        success = delete_profile(profile_name)
        if success:
            logger.info("🗑️ Deleted voice profile: %s", profile_name)
            return {'success': True}
        return {'success': False, 'error': 'Profile not found or protected'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ============================================================================
# BACKGROUND QUEUE
# ============================================================================

@app.get("/api/background/queue")
async def get_background_queue():
    """Get background processor queue status"""
    try:
        bg = bot_state['background_processor']
        if not bg:
            return {'size': 0, 'is_running': False}
        return {
            'size': len(getattr(bg, 'processing_queue', []) or []),
            'is_running': getattr(bg, 'is_running', False),
        }
    except Exception as e:
        return {'error': str(e)}

@app.post("/api/background/clear-queue")
async def clear_background_queue():
    """Clear all pending background tasks"""
    try:
        bg = bot_state['background_processor']
        if not bg:
            return {'success': False, 'error': 'Not initialized'}
        q = getattr(bg, 'processing_queue', None)
        cleared = 0
        if q:
            if isinstance(q, list):
                cleared = len(q)
                q.clear()
            elif hasattr(q, 'qsize'):
                cleared = q.qsize()
                while not q.empty():
                    try:
                        q.get_nowait()
                    except:
                        break
        logger.info("🗑️ Cleared %d background tasks", cleared)
        return {'success': True, 'cleared': cleared}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ============================================================================
# VOICE BEHAVIOR SETTINGS
# ============================================================================

@app.get("/api/voice/behavior/settings")
async def get_voice_behavior_settings():
    """Get voice auto-join/leave behavior settings"""
    try:
        vbm = bot_state['voice_behavior_manager']
        if not vbm:
            return {
                'join_aggressiveness': 0.5,
                'leave_after_silence_seconds': 180,
                'max_session_minutes': 60,
                'enabled': False,
            }
        settings = vbm.get_settings()
        settings['enabled'] = True
        return settings
    except Exception as e:
        return {'error': str(e)}

@app.post("/api/voice/behavior/settings")
async def update_voice_behavior_settings(data: Dict[str, Any]):
    """Update voice auto-join/leave behavior settings"""
    try:
        vbm = bot_state['voice_behavior_manager']
        if not vbm:
            return {'success': False, 'error': 'Voice behavior manager not initialized'}
        vbm.update_settings(data)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.get("/api/voice/behavior/stats")
async def get_voice_behavior_stats():
    """Get voice behavior statistics"""
    try:
        vbm = bot_state['voice_behavior_manager']
        if not vbm:
            return {'auto_joins': 0, 'auto_leaves': 0, 'rejected_joins': 0}
        return vbm.get_stats()
    except Exception as e:
        return {'error': str(e)}

# ============================================================================
# SERVER LIFECYCLE
# ============================================================================

def init_bot_state(
    discord_client: Any,
    message_manager: Any,
    background_processor: Any,
    passive_monitor: Any,
    message_crawler: Any,
    memory_system: Any,
    voice_listener: Optional[Any] = None,
    tts_engine: Optional[Any] = None,
    voice_manager: Optional[Any] = None
) -> None:
    """Initialize bot state for control panel"""
    bot_state['discord_client'] = discord_client
    bot_state['message_manager'] = message_manager
    bot_state['background_processor'] = background_processor
    bot_state['passive_monitor'] = passive_monitor
    bot_state['message_crawler'] = message_crawler
    bot_state['memory_system'] = memory_system
    bot_state['voice_listener'] = voice_listener
    bot_state['tts_engine'] = tts_engine
    bot_state['voice_manager'] = voice_manager
    
    logger.info("✅ Control panel state initialized")


async def start_server(host: str = "127.0.0.1", port: int = 8080):
    """Start web server with port retry logic"""
    if host != "127.0.0.1" and not config.CONTROL_PANEL_KEY:
        logger.warning("Control panel exposed to network without authentication!")
    max_retries = 5
    current_port = port
    
    for i in range(max_retries):
        try:
            uvicorn_cfg = uvicorn.Config(
                app,
                host=host,
                port=current_port,
                log_level="info",
                access_log=False
            )
            server = uvicorn.Server(uvicorn_cfg)
            
            logger.info(f"🌐 Control panel starting at http://{host}:{current_port}")
            await server.serve()
            break  # If successful (or clean exit), stop retrying
            
        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.warning(f"⚠️ Port {current_port} is busy, trying {current_port + 1}...")
                current_port += 1
            else:
                raise e
        except SystemExit:
             # Uvicorn raises SystemExit on startup failure
             logger.warning(f"⚠️ Port {current_port} failed to bind, trying {current_port + 1}...")
             current_port += 1
        except Exception as e:
            # Catch generic startup errors that might be port related
            if "address already in use" in str(e).lower() or "[errno 98]" in str(e).lower():
                logger.warning(f"⚠️ Port {current_port} is busy (error: {e}), trying {current_port + 1}...")
                current_port += 1
            else:
                logger.error(f"❌ Failed to start web server: {e}")
                raise e


# ============================================================================
# HELPER: Inject custom logger handler for WebSocket streaming
# ============================================================================

import logging

class WebSocketLogHandler(logging.Handler):
    """Custom log handler that broadcasts to WebSocket clients"""
    
    def emit(self, record):
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'level': record.levelname,
                'message': record.getMessage()
            }
            
            # Schedule broadcast in event loop safely
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(broadcast_log(log_entry))
            except RuntimeError:
                pass  # Not in an async context, skip broadcast
        except Exception:
            pass  # Silently fail to avoid recursion

# Add handler to logger
ws_handler = WebSocketLogHandler()
ws_handler.setLevel(logging.INFO)
logger.addHandler(ws_handler)
