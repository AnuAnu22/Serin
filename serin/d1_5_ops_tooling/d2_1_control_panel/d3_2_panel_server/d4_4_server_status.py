"""Status, stats, health, and homepage routes for the control panel."""

from __future__ import annotations

from typing import Any

from fastapi.responses import FileResponse, HTMLResponse

from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_1_state_access import (
    get_component,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
    app,
    bot_state,
    make_json_safe,
)


@app.get("/", response_class=HTMLResponse)
async def homepage() -> Any:
    """Serve main dashboard"""
    return FileResponse("control_panel/static/index.html")


@app.get("/api/status")
async def get_status() -> Any:
    """Get current bot status"""
    client = get_component('discord_client')

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
    health: dict[str, Any] = {
        'status': 'healthy',
        'components': {},
        'startup_complete': bool(bot_state),
    }

    # 1. Discord
    client = get_component('discord_client')
    health['components']['discord'] = {
        'status': 'ok' if client and client.is_ready() else 'error',
        'latency': round(client.latency * 1000, 2) if client else 0
    }

    # 2. Memory
    mem = get_component('memory_system')
    health['components']['memory'] = {
        'status': 'ok' if mem else 'error',
        'type': 'Qdrant' if mem and hasattr(mem, 'qdrant_client') else 'Unknown'
    }

    # 3. Voice Input
    listener = get_component('voice_listener')
    health['components']['voice_input'] = {
        'status': 'ok' if listener else 'disabled',
        'connected': listener.is_connected() if listener else False
    }

    # 4. TTS
    tts = get_component('tts_engine')
    health['components']['tts'] = {
        'status': 'ok' if tts and tts.tts else 'disabled',
        'model': tts.model_name if tts else None
    }

    # 5. Background Processor
    bg = get_component('background_processor')
    health['components']['background'] = {
        'status': 'ok' if bg and bg.is_running else 'stopped',
        'queue_size': len(bg.processing_queue) if bg else 0
    }

    if any(c['status'] == 'error' for c in health['components'].values()):
        health['status'] = 'degraded'

    return health


def get_current_stats() -> Any:
    """Helper to get current stats from all systems (JSON-safe)"""
    stats: dict[str, Any] = {}

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
