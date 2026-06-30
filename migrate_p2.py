#!/usr/bin/env python3
"""p2_gateway migration - copies files, updates imports, creates shims."""
import os, re, shutil, sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# ── File copy map: source → target ────────────────────────────────────────────
COPIES = [
    ("discord_bot.py", "p2_gateway/1_discord/1_bot_entry.py"),
    ("voice/tracker.py", "p2_gateway/1_discord/4_voice_tracker.py"),
    ("tts/tts_engine.py", "p2_gateway/2_voice/1_tts_engine.py"),
    ("voice/profiles.py", "p2_gateway/2_voice/1a_voice_profiles.py"),
    ("voice/bridge.py", "p2_gateway/2_voice/2_rust_voice_bridge.py"),
    ("voice/listener.py", "p2_gateway/2_voice/2a_voice_listener.py"),
    ("voice/processor.py", "p2_gateway/2_voice/3_audio_processor.py"),
    ("voice/transcriber.py", "p2_gateway/2_voice/3a_whisper_transcriber.py"),
    ("voice/output.py", "p2_gateway/2_voice/3b_voice_output_manager.py"),
    ("tts_voice_manager.py", "p2_gateway/2_voice/1b_voice_file_manager.py"),
    ("models/lm_studio.py", "p2_gateway/5_adapter/1_lm_studio_connector.py"),
    ("models/sglang.py", "p2_gateway/5_adapter/2_sglang_connector.py"),
    ("models/vllm.py", "p2_gateway/5_adapter/3_vllm_connector.py"),
]

# These 3 are redirect shims → copy from the intermediate locations instead
COPIES_FROM_INTERMEDIATE = [
    ("serin/pipeline/ingest/mention_translator.py", "p2_gateway/1_discord/2_mention_translator.py"),
    ("serin/pipeline/ingest/crawler.py", "p2_gateway/1_discord/2a_message_crawler.py"),
    ("serin/ops/passive_monitor.py", "p2_gateway/1_discord/3_passive_monitor.py"),
]

# ── Import replacements per file (applied via regex) ──────────────────────────
# Key = target filename (basename), Value = list of (pattern, replacement)
IMPORT_UPDATES = {
    "1_bot_entry.py": [
        # Core config
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        (r"from serin\.core\.config import config", "from p4_config.config import config"),
        # p2_gateway internal imports (use importlib since numbered dirs aren't valid Python packages)
        # We'll handle these specially - convert to importlib calls
        # Non-p2 imports → updated intermediate paths
        (r"from serin\.utils\.background import BackgroundProcessor", "from serin.ops.background import BackgroundProcessor"),
        (r"from serin\.utils\.database_protector import get_database_protector", "from serin.ops.database_protector import get_database_protector"),
        (r"from serin\.control_panel\.server import init_bot_state, start_server", "from serin.ops.control_panel.server import init_bot_state, start_server"),
        (r"from serin\.control_panel\.server import bot_state", "from serin.ops.control_panel.server import bot_state"),
        (r"from serin\.control_panel\.server import broadcast_event", "from serin.ops.control_panel.server import broadcast_event"),
        (r"from serin\.utils\.database_protector import DatabaseProtector, DatabaseValidationError, DatabaseRecoveryError", "from serin.ops.database_protector import DatabaseProtector, DatabaseValidationError, DatabaseRecoveryError"),
        (r"from serin\.messaging\.pipeline import MessagePipeline", "from serin.pipeline.act.pipeline import MessagePipeline"),
        (r"from serin\.utils\.thinking_filter import get_thinking_filter", "from p3_state.thinking_filter import get_thinking_filter"),
        (r"from serin\.messaging\.response_generator import initialize_llama", "from serin.pipeline.think.response_generator import initialize_llama"),
        (r"import serin\.messaging\.response_generator", "import serin.pipeline.think.response_generator"),
        (r"from serin\.messaging\.response_generator import get_response_natural", "from serin.pipeline.think.response_generator import get_response_natural"),
        (r"from serin\.messaging\.manager import EnhancedMessageManagerV3", "from serin.pipeline.ingest.manager import EnhancedMessageManagerV3"),
        (r"from voice\.pipeline import VoiceMemoryPipeline", "from serin.pipeline.remember.voice_memory_pipeline import VoiceMemoryPipeline"),
        (r"from voice\.behavior import VoiceBehaviorManager", "from serin.pipeline.think.voice_behavior import VoiceBehaviorManager"),
        (r"from serin\.memory\.qdrant import QdrantMemorySystem", "from serin.pipeline.remember.qdrant import QdrantMemorySystem"),
        (r"from serin\.memory\.sync_monitor import MemorySyncMonitor", "from serin.pipeline.remember.sync_monitor import MemorySyncMonitor"),
        (r"serin\.messaging\.response_generator\.llama", "serin.pipeline.think.response_generator.llama"),
        (r"serin\.messaging\.response_generator\.discord_client", "serin.pipeline.think.response_generator.discord_client"),
    ],
    "4_voice_tracker.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        (r"from serin\.utils\.debug_logger import log_voice", "from p4_config.debug_logger import log_voice"),
    ],
    "1_tts_engine.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
    ],
    "1a_voice_profiles.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
    ],
    "2_rust_voice_bridge.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
    ],
    "2a_voice_listener.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
    ],
    "3_audio_processor.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
    ],
    "3a_whisper_transcriber.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
    ],
    "3b_voice_output_manager.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
    ],
    "1b_voice_file_manager.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
    ],
    "1_lm_studio_connector.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        (r"from \.model_interface import ModelInterface", "from p3_state.model_interface import ModelInterface"),
        (r"from \.model_adapter import ModelAdapter", "from models.model_adapter import ModelAdapter"),
    ],
    "2_sglang_connector.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        (r"from \.model_interface import ModelInterface", "from p3_state.model_interface import ModelInterface"),
        (r"from \.model_adapter import ModelAdapter", "from models.model_adapter import ModelAdapter"),
    ],
    "3_vllm_connector.py": [
        (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        (r"from \.model_interface import ModelInterface", "from p3_state.model_interface import ModelInterface"),
        (r"from \.model_adapter import ModelAdapter", "from models.model_adapter import ModelAdapter"),
    ],
    # Files copied from intermediate locations
    "2_mention_translator.py": [
        (r"from serin\.config\.logger import logger", "from p4_config.logger import logger"),
    ],
    "2a_message_crawler.py": [
        (r"from serin\.config\.logger import logger", "from p4_config.logger import logger"),
    ],
    "3_passive_monitor.py": [
        (r"from serin\.config\.logger import logger", "from p4_config.logger import logger"),
    ],
}

# ── Special handling for bot_entry.py p2_gateway internal imports ──────────────
# Since numbered dirs can't be Python packages, we convert these to importlib
BOT_ENTRY_P2_IMPORTS = [
    (r"from serin\.messaging\.mention_translator import MentionTranslator",
     "from p2_gateway import MentionTranslator"),
    (r"from serin\.utils\.passive_monitor import PassiveMonitor",
     "from p2_gateway import PassiveMonitor"),
    (r"from serin\.messaging\.crawler import MessageCrawler",
     "from p2_gateway import MessageCrawler"),
    (r"from voice\.listener import VoiceListener",
     "from p2_gateway import VoiceListener"),
    (r"from voice\.processor import AudioStreamProcessor",
     "from p2_gateway import AudioStreamProcessor"),
    (r"from voice\.transcriber import WhisperTranscriber",
     "from p2_gateway import WhisperTranscriber"),
    (r"from voice\.output import VoiceOutputManager",
     "from p2_gateway import VoiceOutputManager"),
    (r"from tts\.tts_engine import TTSEngine",
     "from p2_gateway import TTSEngine"),
    (r"from tts_voice_manager import TTSVoiceManager",
     "from p2_gateway import TTSVoiceManager"),
]

# Cross-import within p2_gateway: listener imports bridge
LISTENER_CROSS_IMPORT = [
    (r"from voice\.bridge import RustVoiceBridge",
     "from p2_gateway import RustVoiceBridge"),
]

# Shim targets: old_path → (class_or_name, new_module_base)
# These create backward-compat shims at old locations
SHIMS = {
    "serin/messaging/mention_translator.py": "MentionTranslator",
    "serin/messaging/crawler.py": "MessageCrawler",
    "serin/utils/passive_monitor.py": "PassiveMonitor",
    "voice/tracker.py": "VoiceTracker",
    "tts/tts_engine.py": "TTSEngine",
    "voice/profiles.py": None,  # Multiple exports
    "voice/bridge.py": "RustVoiceBridge",
    "voice/listener.py": "VoiceListener",
    "voice/processor.py": "AudioStreamProcessor",
    "voice/transcriber.py": "WhisperTranscriber",
    "voice/output.py": "VoiceOutputManager",
    "tts_voice_manager.py": "TTSVoiceManager",
    "models/lm_studio.py": "LMStudioConnector",
    "models/sglang.py": "SGLangConnector",
    "models/vllm.py": "VLLMConnector",
    "discord_bot.py": None,  # main entry point
}


def apply_updates(content, updates):
    for pat, repl in updates:
        content = re.sub(pat, repl, content)
    return content


def read_file(path):
    with open(os.path.join(ROOT, path)) as f:
        return f.read()


def write_file(path, content):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


def is_redirect_shim(path):
    """Check if a source file is already a redirect shim (not real code)."""
    try:
        content = read_file(path)
        return content.strip().startswith('"""Redirect')
    except FileNotFoundError:
        return False


def main():
    os.chdir(ROOT)

    # ── Step 1: Copy files ────────────────────────────────────────────────
    print("STEP 1: Copy files")
    copied = {}
    for src, dst in COPIES + COPIES_FROM_INTERMEDIATE:
        src_path = os.path.join(ROOT, src)
        # If original is a shim (from prior run), try .bak file
        if is_redirect_shim(src):
            bak = src_path + ".bak"
            if os.path.exists(bak):
                src_path = bak
                print(f"  Using backup: {src}.bak")
            else:
                print(f"  SKIP (shim, no backup): {src}")
                continue
        elif not os.path.exists(src_path):
            print(f"  SKIP (missing): {src}")
            continue
        content = open(src_path).read()
        basename = os.path.basename(dst)
        # Apply import updates
        updates = IMPORT_UPDATES.get(basename, [])
        content = apply_updates(content, updates)
        # Special: bot_entry p2 internal imports
        if basename == "1_bot_entry.py":
            content = apply_updates(content, BOT_ENTRY_P2_IMPORTS)
        # Special: listener cross-import
        if basename == "2a_voice_listener.py":
            content = apply_updates(content, LISTENER_CROSS_IMPORT)
        write_file(dst, content)
        copied[dst] = basename
        print(f"  OK: {src} → {dst}")

    # ── Step 2: Create p2_gateway/__init__.py ─────────────────────────────
    print("\nSTEP 2: Create p2_gateway/__init__.py (importlib loader)")
    init_content = '''"""
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
'''
    write_file("p2_gateway/__init__.py", init_content)
    print("  Created p2_gateway/__init__.py")

    # ── Step 3: Create empty __init__.py in subdirs (for importlib path resolution) ─
    print("\nSTEP 3: Create subdir __init__.py files")
    for subdir in ["1_discord", "2_voice", "3_text", "4_media", "5_adapter"]:
        path = f"p2_gateway/{subdir}/__init__.py"
        write_file(path, "")
        print(f"  Created {path}")

    # ── Step 4: Backward-compat shims ─────────────────────────────────────
    print("\nSTEP 4: Create backward-compat shims")
    shim_map = {
        "serin/messaging/mention_translator.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import MentionTranslator\n',
        "serin/messaging/crawler.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import MessageCrawler\n',
        "serin/utils/passive_monitor.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import PassiveMonitor\n',
        "voice/tracker.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import VoiceTracker\n',
        "tts/tts_engine.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import TTSEngine\n',
        "voice/profiles.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import (VoiceProfile, VoiceProfileManager, get_profile_manager,\n'
            '    get_voice_profiles, get_active_profile_name, create_profile,\n'
            '    set_active_profile, delete_profile)\n',
        "voice/bridge.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import RustVoiceBridge, RustStdoutReader\n',
        "voice/listener.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import VoiceListener, InfoCaptureProtocol\n',
        "voice/processor.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import AudioStreamProcessor\n',
        "voice/transcriber.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import WhisperTranscriber\n',
        "voice/output.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import VoiceOutputManager\n',
        "tts_voice_manager.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import TTSVoiceManager\n',
        "models/lm_studio.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import LMStudioConnector\n',
        "models/sglang.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import SGLangConnector\n',
        "models/vllm.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway import VLLMConnector\n',
        "discord_bot.py":
            '"""Redirect — moved to p2_gateway. Update your imports."""\n'
            'from p2_gateway.1_discord.1_bot_entry import main, client  # noqa\n',
    }
    for old_path, shim_content in shim_map.items():
        full_old = os.path.join(ROOT, old_path)
        if os.path.exists(full_old):
            with open(full_old) as f:
                existing = f.read()
            if existing.strip() == shim_content.strip():
                print(f"  SKIP (already): {old_path}")
                continue
            backup = full_old + ".bak"
            if not os.path.exists(backup):
                shutil.copy2(full_old, backup)
        write_file(old_path, shim_content)
        print(f"  Shim: {old_path}")

    # ── Step 5: Verify ────────────────────────────────────────────────────
    print("\nSTEP 5: Verification")
    for src, dst in COPIES + COPIES_FROM_INTERMEDIATE:
        basename = os.path.basename(dst)
        full_dst = os.path.join(ROOT, dst)
        if not os.path.exists(full_dst):
            print(f"  MISSING: {dst}")
            continue
        content = read_file(dst.replace(ROOT + "/", ""))
        # Check for SyntaxError-prone imports (from p2_gateway.N_...)
        bad = re.findall(r"from p2_gateway\.\d+_\w+", content)
        if bad:
            print(f"  SYNTAX ERROR: {dst} has: {bad}")
        old_refs = re.findall(r"from serin\.core\.", content)
        if old_refs:
            print(f"  STALE: {dst} still references serin.core")
        else:
            print(f"  OK: {dst}")

    # Syntax check
    print("\nSyntax check:")
    for src, dst in COPIES + COPIES_FROM_INTERMEDIATE:
        basename = os.path.basename(dst)
        full = os.path.join(ROOT, dst)
        try:
            with open(full) as f:
                ast_content = f.read()
            compile(ast_content, full, "exec")
            print(f"  PASS: {dst}")
        except SyntaxError as e:
            print(f"  FAIL: {dst} — {e}")

    print("\nDone!")


if __name__ == "__main__":
    main()
