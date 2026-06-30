"""
p2_gateway — External Interfaces (Discord, Voice, Adapters)

Because subdirectory names (1_discord, 2_voice, 5_adapter) start with digits,
they cannot be used as Python package names in import statements. This __init__.py
uses importlib to load all submodules and re-export their public APIs.
"""
import importlib
import os as _os

_dir = _os.path.dirname(_os.path.abspath(__file__))

def _load(subdir, module_name):
    """Dynamically load a module from a numbered subdirectory."""
    mod_path = _os.path.join(_dir, subdir, f"{module_name}.py")
    if not _os.path.exists(mod_path):
        return None
    # importlib can handle numeric-prefix names that syntax can't
    qualified = f"p2_gateway.{subdir}.{module_name}"
    try:
        return importlib.import_module(qualified)
    except (ImportError, ModuleNotFoundError):
        # Fallback: load directly from file path
        import importlib.util
        spec = importlib.util.spec_from_file_location(qualified, mod_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None

# ── 1_discord ────────────────────────────────────────────────────────────────
_m = _load("1_discord", "2_mention_translator")
if _m: MentionTranslator = _m.MentionTranslator

_m = _load("1_discord", "2a_message_crawler")
if _m: MessageCrawler = _m.MessageCrawler

_m = _load("1_discord", "3_passive_monitor")
if _m: PassiveMonitor = _m.PassiveMonitor

_m = _load("1_discord", "4_voice_tracker")
if _m:
    VoiceTracker = _m.VoiceTracker
    get_voice_join_reaction = _m.get_voice_join_reaction
    get_voice_duration_reaction = _m.get_voice_duration_reaction

# ── 2_voice ──────────────────────────────────────────────────────────────────
_m = _load("2_voice", "1_tts_engine")
if _m: TTSEngine = _m.TTSEngine

_m = _load("2_voice", "1a_voice_profiles")
if _m:
    VoiceProfile = _m.VoiceProfile
    VoiceProfileManager = _m.VoiceProfileManager
    get_profile_manager = _m.get_profile_manager
    get_voice_profiles = _m.get_voice_profiles
    get_active_profile_name = _m.get_active_profile_name
    create_profile = _m.create_profile
    set_active_profile = _m.set_active_profile
    delete_profile = _m.delete_profile

_m = _load("2_voice", "2_rust_voice_bridge")
if _m:
    RustVoiceBridge = _m.RustVoiceBridge
    RustStdoutReader = _m.RustStdoutReader

_m = _load("2_voice", "2a_voice_listener")
if _m:
    VoiceListener = _m.VoiceListener
    InfoCaptureProtocol = _m.InfoCaptureProtocol

_m = _load("2_voice", "3_audio_processor")
if _m: AudioStreamProcessor = _m.AudioStreamProcessor

_m = _load("2_voice", "3a_whisper_transcriber")
if _m:
    WhisperTranscriber = _m.WhisperTranscriber
    WhisperTranscriberFallback = _m.WhisperTranscriberFallback

_m = _load("2_voice", "3b_voice_output_manager")
if _m: VoiceOutputManager = _m.VoiceOutputManager

_m = _load("2_voice", "1b_voice_file_manager")
if _m: TTSVoiceManager = _m.TTSVoiceManager

# ── 5_adapter ────────────────────────────────────────────────────────────────
_m = _load("5_adapter", "1_lm_studio_connector")
if _m: LMStudioConnector = _m.LMStudioConnector

_m = _load("5_adapter", "2_sglang_connector")
if _m: SGLangConnector = _m.SGLangConnector

_m = _load("5_adapter", "3_vllm_connector")
if _m: VLLMConnector = _m.VLLMConnector
