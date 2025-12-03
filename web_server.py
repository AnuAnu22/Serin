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
from typing import Optional, Dict, Any
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from logger_config import logger
from enhanced_api_routes import register_enhanced_routes
from starlette.websockets import WebSocketDisconnect
import json

def make_json_safe(obj):
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
            stats = get_current_stats()
            await websocket.send_json({
                'type': 'stats_update',
                'data': stats
            })
        except Exception as e:
            logger.error(f"Error sending initial stats: {e}")
            raise  # Exit if we can't even send initial data
        
        while True:
            # Wait for messages from client (keep-alive)
            try:
                # Wait with timeout to detect disconnection
                await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                # No message received, send stats update
                pass
            except Exception as e:
                # Connection closed
                logger.debug(f"WebSocket receive error: {e}")
                break
            
            # Only send if connection is still open
            try:
                # Check state before sending
                if not websocket.client_state.value == 1:  # CONNECTED
                    break
                    
                stats = get_current_stats()
                await websocket.send_json({
                    'type': 'stats_update',
                    'data': stats
                })
            except Exception as e:
                logger.debug(f"Error sending stats: {e}")
                break  # Exit on any send error
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        try:
            await websocket.close()
        except:
            pass
        logger.info(f"🌐 WebSocket disconnected (remaining: {len(active_websockets)})")

async def broadcast_log(log_entry: Dict):
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
                'data': log_entry
            })
        except Exception:
            to_remove.append(ws)
    
    # Remove disconnected
    for ws in to_remove:
        if ws in active_websockets:
            active_websockets.remove(ws)


async def broadcast_event(event_type: str, data: Dict):
    """Broadcast event to all connected WebSockets"""
    to_remove = []
    
    for ws in active_websockets:
        try:
            # Check if connection is still open
            if ws.client_state.value != 1:
                to_remove.append(ws)
                continue
                
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

def get_current_stats() -> Dict:
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
        from config import config
        return config.to_dict()
    except Exception as e:
        return {'error': str(e)}

@app.post("/api/config")
async def update_full_config(data: Dict[str, Any]):
    """Update bot configuration"""
    try:
        from config import config
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
        from config import config
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
# SERVER LIFECYCLE
# ============================================================================

def init_bot_state(
    discord_client,
    message_manager,
    background_processor,
    passive_monitor,
    message_crawler,
    memory_system,
    voice_listener=None,
    tts_engine=None,
    voice_manager=None
):
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
    """Start web server"""
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(config)
    
    logger.info(f"🌐 Control panel starting at http://{host}:{port}")
    await server.serve()


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
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(broadcast_log(log_entry))
        except Exception:
            pass  # Silently fail to avoid recursion

# Add handler to logger
ws_handler = WebSocketLogHandler()
ws_handler.setLevel(logging.INFO)
logger.addHandler(ws_handler)
