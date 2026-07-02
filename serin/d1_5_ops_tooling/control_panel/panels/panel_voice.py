import asyncio
import os
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel

from serin.d1_3_state_core.logger import logger
from serin.d1_4_config_base.config import config


class _RouteApp(Protocol):
    def get(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...
    def post(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


def register_voice_routes(app: _RouteApp) -> None:
    """Register voice management routes."""
    from serin.d1_5_ops_tooling.control_panel.server import (
        ChannelControl,
        MemoryQuery,
        SettingsUpdate,
        VoiceChannelControl,
        VoiceLoad,
        bot_state,
        broadcast_event,
    )

    @app.post("/api/channels/allowed")
    async def update_allowed_channels(control: ChannelControl) -> Any:
        """Add or remove allowed channel"""
        try:
            channel_id = int(control.channel_id)

            if control.action == 'add':
                config.ALLOWED_CHANNEL_IDS.add(channel_id)
            elif control.action == 'remove':
                config.ALLOWED_CHANNEL_IDS.discard(channel_id)
            else:
                return {'success': False, 'error': 'Invalid action'}

            logger.info(f" Channel {control.action}: {channel_id}")
            return {
                'success': True,
                'channels': [str(cid) for cid in config.ALLOWED_CHANNEL_IDS]
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


    # ============================================================================
    # VOICE CONTROL (TIER 6)
    # ============================================================================

    @app.get("/api/voice/channels")
    async def get_voice_channels() -> Any:
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
    async def join_voice_channel(control: VoiceChannelControl) -> Any:
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
                logger.info(f" Joined voice channel: {control.channel_id}")
                await broadcast_event('voice_joined', {
                    'guild_id': control.guild_id,
                    'channel_id': control.channel_id
                })

            return {'success': success}
        except Exception as e:
            logger.error(f"Error joining voice: {e}")
            return {'success': False, 'error': str(e)}


    @app.post("/api/voice/leave")
    async def leave_voice_channel(control: VoiceChannelControl) -> Any:
        """Leave a voice channel"""
        try:
            voice_listener = bot_state['voice_listener']
            if not voice_listener:
                return {'success': False, 'error': 'Voice listener not initialized'}

            success = await voice_listener.leave_channel(int(control.guild_id))

            if success:
                logger.info(f" Left voice channel in guild: {control.guild_id}")
                await broadcast_event('voice_left', {
                    'guild_id': control.guild_id
                })

            return {'success': success}
        except Exception as e:
            return {'success': False, 'error': str(e)}


    @app.get("/api/voice/status")
    async def get_voice_status() -> Any:
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
    async def list_voice_files() -> Any:
        """List available voice files"""
        try:
            manager = bot_state['voice_manager']
            if not manager:
                return {'voices': []}

            return {'voices': manager.list_voices()}
        except Exception as e:
            return {'error': str(e)}

    @app.post("/api/voice/load")
    async def load_voice_file(data: VoiceLoad) -> Any:
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
    async def clear_voice_file() -> Any:
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
    async def search_memories(query: MemoryQuery) -> Any:
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
    async def get_all_users() -> Any:
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
    async def get_user_profile(user_id: str) -> Any:
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
    async def get_brain_state() -> Any:
        """Get current brain state (thinking, generating, etc.)"""
        try:
            manager = bot_state['message_manager']
            if not manager:
                return {'status': 'OFFLINE'}

            return manager.current_state
        except Exception as e:
            return {'error': str(e)}

    @app.post("/api/brain/abort")
    async def abort_generation() -> Any:
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
    async def emergency_stop() -> Any:
        """Emergency stop alias"""
        return await abort_generation()

    @app.post("/api/bot/restart")
    async def restart_bot() -> Any:
        """Restart the bot process (hot-reloads code changes). The hot_reloader.py wrapper will auto-restart."""
        try:
            from serin.d1_5_ops_tooling.hot_reloader import SIGNAL_FILE
            open(SIGNAL_FILE, "w").close()
            logger.warning(" Restart signal sent to hot-reloader")
            return {'success': True, 'message': 'Restart signal sent'}
        except Exception as e:
            logger.error(f"Failed to send restart signal: {e}")
            return {'success': False, 'error': str(e)}

    class MoodRequest(BaseModel):
        mood: str

    @app.post("/api/mood/set")
    async def set_mood(request: MoodRequest) -> Any:
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
    async def sever_context(request: ContextSeverRequest) -> Any:
        """Sever proactive context for a channel"""
        try:
            manager = bot_state['message_manager']
            if not manager or not hasattr(manager, 'response_controller'):
                 return {'success': False, 'error': 'Manager not initialized'}

            rc = manager.response_controller
            if request.channel_id in rc.active_conversations:
                del rc.active_conversations[request.channel_id]
                logger.info(f"✂ Severed context for {request.channel_id}")
                return {'success': True}

            return {'success': False, 'error': 'Context not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @app.get("/api/system_prompt")
    async def get_system_prompt() -> Any:
        """Get current system prompt"""
        try:
            manager = bot_state['message_manager']
            if not manager:
                return {'prompt': ''}

            return {'prompt': manager.system_prompt}
        except Exception as e:
            return {'error': str(e)}

    @app.post("/api/system_prompt")
    async def update_system_prompt(data: dict[str, str]) -> Any:
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
    async def get_full_config() -> Any:
        """Get full bot configuration"""
        try:
            return config.to_dict()
        except Exception as e:
            return {'error': str(e)}

    @app.post("/api/config")
    async def update_full_config(data: dict[str, Any]) -> Any:
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
    async def get_settings() -> Any:
        """Get all configurable settings (Legacy)"""
        return await get_full_config()

    @app.post("/api/settings/update")
    async def update_setting(update: SettingsUpdate) -> Any:
        """Update a setting (Legacy wrapper)"""
        try:
            from serin.d1_4_config_base.config import config
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
    async def get_recent_logs() -> Any:
        """Get recent log entries"""
        try:
            # Read last 100 lines from log file
            log_file = "bot.log"
            if not os.path.exists(log_file):
                return {'logs': []}

            with open(log_file) as f:
                lines = f.readlines()[-100:]

            return {'logs': lines}
        except Exception as e:
            return {'error': str(e)}


    # ============================================================================
    # CRAWLER CONTROL
    # ============================================================================

    @app.post("/api/crawler/trigger-sync")
    async def trigger_manual_sync() -> Any:
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


    async def _run_manual_sync(crawler: Any) -> None:
        """Background task for manual sync"""
        try:
            logger.info(" Manual sync triggered from control panel")
            client = bot_state['discord_client']

            synced_count = 0
            for guild in client.guilds:
                for channel in guild.text_channels:
                    try:
                        synced = await crawler._quick_sync_channel(channel)
                        synced_count += synced
                    except Exception:
                        logger.exception("Failed to quick-sync channel during manual sync")

            logger.info(f" Manual sync complete: {synced_count} messages")
            await broadcast_event('sync_complete', {'count': synced_count})
        except Exception as e:
            logger.error(f"Error in manual sync: {e}")


    # ============================================================================
    # TTS CONTROL
    # ============================================================================
