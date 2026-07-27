from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from serin.d1_4_config_base.d2_3_core_logger import logger


class _RouteApp(Protocol):
    def get(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...
    def post(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...
    def delete(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


def register_control_routes(app: _RouteApp) -> None:
    """Register TTS, profile, settings routes."""
    """TTS, voice profiles, behavior, settings, and background endpoints."""
    @app.get("/api/tts/voices")
    async def list_tts_voices() -> Any:
        """List available TTS voice files"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
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
                logger.exception("Failed to list edge-tts voices")
            return {'voices': []}
        except Exception as e:
            return {'error': str(e)}

    @app.get("/api/tts/current")
    async def get_current_tts() -> Any:
        """Get current TTS engine status"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
                make_json_safe,
            )
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
    async def load_tts_voice(data: dict[str, Any]) -> Any:
        """Load a TTS voice file"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
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
    async def clear_tts_voice() -> Any:
        """Clear custom TTS voice, revert to default"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
            tts = bot_state['tts_engine']
            if not tts:
                return {'success': False, 'error': 'TTS not initialized'}
            if hasattr(tts, 'clear_voice'):
                await tts.clear_voice()
                return {'success': True}
            return {'success': False, 'error': 'clear_voice not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @app.post("/api/tts/voice/test")
    async def test_tts_voice() -> Any:
        """Test TTS by synthesizing a test phrase"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
            tts = bot_state['tts_engine']
            if not tts:
                return {'success': False, 'error': 'TTS not initialized'}
            if hasattr(tts, 'synthesize') and callable(tts.synthesize):
                await tts.synthesize("Hello, I am Serin. This is a test of the text to speech system.")
                return {'success': True}
            if hasattr(tts, 'generate_speech') and callable(tts.generate_speech):
                await tts.generate_speech("Hello, I am Serin. This is a test of the text to speech system.")
                return {'success': True}
            return {'success': False, 'error': 'No synthesize method available on TTS engine'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


    @app.post("/api/tts/settings/update")
    async def update_tts_settings(data: dict[str, Any]) -> Any:
        """Update TTS settings (profile, speed, etc.)"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
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
    async def get_audio_settings() -> Any:
        """Get audio processing settings"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
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

    # Sane bounds for the VAD tuning knobs. These aren't arbitrary — see
    # docs/ARCHITECTURE.md's VAD section: threshold is RMS amplitude at 50fps,
    # default 150; silence_threshold is seconds of silence before the
    # pipeline queues audio for transcription, default ~1.5-3s. A threshold
    # of 0 makes VAD constantly fire on room noise; a negative or zero silence
    # window means audio never accumulates before being flushed.
    _vad_threshold_range = (10, 2000)
    _silence_threshold_range = (0.2, 30.0)

    @app.post("/api/audio/settings/update")
    async def update_audio_settings(data: dict[str, Any]) -> Any:
        """Update audio processing settings (validated — see range comment above)."""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
            listener = bot_state.get('voice_listener')
            if not listener:
                return {'success': False, 'error': 'Voice listener not initialized'}
            ap = getattr(listener, 'audio_processor', None)

            if 'vad_threshold' in data and ap:
                value = int(data['vad_threshold'])
                lo, hi = _vad_threshold_range
                if not (lo <= value <= hi):
                    return {'success': False, 'error': f'vad_threshold must be between {lo} and {hi}'}
                ap.VAD_THRESHOLD = value

            if 'silence_threshold' in data and ap:
                value_f = float(data['silence_threshold'])
                lo_f, hi_f = _silence_threshold_range
                if not (lo_f <= value_f <= hi_f):
                    return {'success': False, 'error': f'silence_threshold must be between {lo_f} and {hi_f}'}
                ap.silence_threshold = value_f

            if 'transcription_enabled' in data:
                listener.transcription_enabled = bool(data['transcription_enabled'])

            logger.info(" Audio settings updated from web panel: %s", {k: v for k, v in data.items()})
            return {'success': True}
        except (TypeError, ValueError) as e:
            return {'success': False, 'error': f'Invalid value: {e}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @app.get("/api/audio/stats")
    async def get_audio_stats() -> Any:
        """Get audio processing statistics"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
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
    async def get_active_speakers() -> Any:
        """Get currently active/streaming speakers"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
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
    async def list_voice_profiles() -> Any:
        """List all voice profiles"""
        try:
            from serin.d1_3_state_core.d2_4_core_voice.d3_3_voice_profiles import (
                get_active_profile_name,
                get_voice_profiles,
            )
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
    async def create_voice_profile(data: dict[str, Any]) -> Any:
        """Create a new voice profile"""
        try:
            from serin.d1_3_state_core.d2_4_core_voice.d3_3_voice_profiles import (
                create_profile,
            )
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
                logger.info(" Voice profile created: %s", name)
                return {'success': True}
            return {'success': False, 'error': 'Failed to create profile'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @app.post("/api/voice-profiles/set-active")
    async def set_active_voice_profile(profile_name: str = 'default') -> Any:
        """Set active voice profile"""
        try:
            from serin.d1_3_state_core.d2_4_core_voice.d3_3_voice_profiles import (
                set_active_profile,
            )
            success = set_active_profile(profile_name)
            if success:
                logger.info(" Active voice profile: %s", profile_name)
                return {'success': True}
            return {'success': False, 'error': 'Profile not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @app.delete("/api/voice-profiles/{profile_name}")
    async def delete_voice_profile(profile_name: str) -> Any:
        """Delete a voice profile"""
        try:
            from serin.d1_3_state_core.d2_4_core_voice.d3_3_voice_profiles import (
                delete_profile,
            )
            success = delete_profile(profile_name)
            if success:
                logger.info(" Deleted voice profile: %s", profile_name)
                return {'success': True}
            return {'success': False, 'error': 'Profile not found or protected'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================================
    # BACKGROUND QUEUE
    # ============================================================================

    @app.get("/api/background/queue")
    async def get_background_queue() -> Any:
        """Get background processor queue status"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
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
    async def clear_background_queue() -> Any:
        """Clear all pending background tasks"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
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
                        except Exception:
                            break
            logger.info(" Cleared %d background tasks", cleared)
            return {'success': True, 'cleared': cleared}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ============================================================================
    # VOICE BEHAVIOR SETTINGS
    # ============================================================================

    @app.get("/api/voice/behavior/settings")
    async def get_voice_behavior_settings() -> Any:
        """Get voice auto-join/leave behavior settings"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
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
    async def update_voice_behavior_settings(data: dict[str, Any]) -> Any:
        """Update voice auto-join/leave behavior settings"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
            vbm = bot_state['voice_behavior_manager']
            if not vbm:
                return {'success': False, 'error': 'Voice behavior manager not initialized'}
            vbm.update_settings(data)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @app.get("/api/voice/behavior/stats")
    async def get_voice_behavior_stats() -> Any:
        """Get voice behavior statistics"""
        try:
            from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import (
                bot_state,
            )
            vbm = bot_state['voice_behavior_manager']
            if not vbm:
                return {'auto_joins': 0, 'auto_leaves': 0, 'rejected_joins': 0}
            return vbm.get_stats()
        except Exception as e:
            return {'error': str(e)}

    # ============================================================================
    # SERVER LIFECYCLE
    # ============================================================================
