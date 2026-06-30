#!/usr/bin/env python3
"""One-shot p2_gateway migration script."""
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))

# ── File mappings: source → (target, import_updates) ─────────────────────────
# import_updates: list of (old_pattern, new_replacement) for sed-like regex replacement
MAPPING = {
    "discord_bot.py": (
        "p2_gateway/1_discord/1_bot_entry.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
            (r"from serin\.core\.config import config", "from p4_config.config import config"),
            (r"from serin\.messaging\.mention_translator import MentionTranslator",
             "from p2_gateway.1_discord.2_mention_translator import MentionTranslator"),
            (r"from serin\.utils\.passive_monitor import PassiveMonitor",
             "from p2_gateway.1_discord.3_passive_monitor import PassiveMonitor"),
            (r"from serin\.messaging\.crawler import MessageCrawler",
             "from p2_gateway.1_discord.2a_message_crawler import MessageCrawler"),
            (r"from voice\.listener import VoiceListener",
             "from p2_gateway.2_voice.2a_voice_listener import VoiceListener"),
            (r"from voice\.processor import AudioStreamProcessor",
             "from p2_gateway.2_voice.3_audio_processor import AudioStreamProcessor"),
            (r"from voice\.transcriber import WhisperTranscriber",
             "from p2_gateway.2_voice.3a_whisper_transcriber import WhisperTranscriber"),
            (r"from voice\.output import VoiceOutputManager",
             "from p2_gateway.2_voice.3b_voice_output_manager import VoiceOutputManager"),
            (r"from tts\.tts_engine import TTSEngine",
             "from p2_gateway.2_voice.1_tts_engine import TTSEngine"),
            (r"from tts_voice_manager import TTSVoiceManager",
             "from p2_gateway.2_voice.1b_voice_file_manager import TTSVoiceManager"),
            # Non-p2 imports updated to match intermediate state
            (r"from serin\.utils\.background import BackgroundProcessor",
             "from serin.ops.background import BackgroundProcessor"),
            (r"from serin\.utils\.database_protector import get_database_protector",
             "from serin.ops.database_protector import get_database_protector"),
            (r"from serin\.control_panel\.server import init_bot_state, start_server",
             "from serin.ops.control_panel.server import init_bot_state, start_server"),
            (r"from serin\.control_panel\.server import bot_state",
             "from serin.ops.control_panel.server import bot_state"),
            (r"from serin\.control_panel\.server import broadcast_event",
             "from serin.ops.control_panel.server import broadcast_event"),
            (r"from serin\.utils\.database_protector import DatabaseProtector, DatabaseValidationError, DatabaseRecoveryError",
             "from serin.ops.database_protector import DatabaseProtector, DatabaseValidationError, DatabaseRecoveryError"),
            (r"from serin\.messaging\.pipeline import MessagePipeline",
             "from serin.pipeline.act.pipeline import MessagePipeline"),
            (r"from serin\.utils\.thinking_filter import get_thinking_filter",
             "from p3_state.thinking_filter import get_thinking_filter"),
            (r"from serin\.messaging\.response_generator import initialize_llama",
             "from serin.pipeline.think.response_generator import initialize_llama"),
            (r"import serin\.messaging\.response_generator",
             "import serin.pipeline.think.response_generator"),
            (r"from serin\.messaging\.response_generator import get_response_natural",
             "from serin.pipeline.think.response_generator import get_response_natural"),
            (r"from serin\.messaging\.manager import EnhancedMessageManagerV3",
             "from serin.pipeline.ingest.manager import EnhancedMessageManagerV3"),
            (r"from voice\.pipeline import VoiceMemoryPipeline",
             "from serin.pipeline.remember.voice_memory_pipeline import VoiceMemoryPipeline"),
            (r"from voice\.behavior import VoiceBehaviorManager",
             "from serin.pipeline.think.voice_behavior import VoiceBehaviorManager"),
            (r"from serin\.memory\.qdrant import QdrantMemorySystem",
             "from serin.pipeline.remember.qdrant import QdrantMemorySystem"),
            (r"from serin\.memory\.sync_monitor import MemorySyncMonitor",
             "from serin.pipeline.remember.sync_monitor import MemorySyncMonitor"),
            # Fix serin.messaging.response_generator references in body
            (r"serin\.messaging\.response_generator\.llama", "serin.pipeline.think.response_generator.llama"),
            (r"serin\.messaging\.response_generator\.discord_client", "serin.pipeline.think.response_generator.discord_client"),
        ],
    ),
    "serin/messaging/mention_translator.py": (
        "p2_gateway/1_discord/2_mention_translator.py",
        [],  # This is a redirect shim, we'll handle separately
    ),
    "serin/messaging/crawler.py": (
        "p2_gateway/1_discord/2a_message_crawler.py",
        [],  # This is a redirect shim, we'll handle separately
    ),
    "serin/utils/passive_monitor.py": (
        "p2_gateway/1_discord/3_passive_monitor.py",
        [],  # This is a redirect shim, we'll handle separately
    ),
    "voice/tracker.py": (
        "p2_gateway/1_discord/4_voice_tracker.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
            (r"from serin\.utils\.debug_logger import log_voice", "from p4_config.debug_logger import log_voice"),
        ],
    ),
    "tts/tts_engine.py": (
        "p2_gateway/2_voice/1_tts_engine.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        ],
    ),
    "voice/profiles.py": (
        "p2_gateway/2_voice/1a_voice_profiles.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        ],
    ),
    "voice/bridge.py": (
        "p2_gateway/2_voice/2_rust_voice_bridge.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        ],
    ),
    "voice/listener.py": (
        "p2_gateway/2_voice/2a_voice_listener.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
            (r"from voice\.bridge import RustVoiceBridge",
             "from p2_gateway.2_voice.2_rust_voice_bridge import RustVoiceBridge"),
        ],
    ),
    "voice/processor.py": (
        "p2_gateway/2_voice/3_audio_processor.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        ],
    ),
    "voice/transcriber.py": (
        "p2_gateway/2_voice/3a_whisper_transcriber.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        ],
    ),
    "voice/output.py": (
        "p2_gateway/2_voice/3b_voice_output_manager.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        ],
    ),
    "tts_voice_manager.py": (
        "p2_gateway/2_voice/1b_voice_file_manager.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
        ],
    ),
    "models/lm_studio.py": (
        "p2_gateway/5_adapter/1_lm_studio_connector.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
            (r"from \.model_interface import ModelInterface", "from p3_state.model_interface import ModelInterface"),
            (r"from \.model_adapter import ModelAdapter", "from models.model_adapter import ModelAdapter"),
        ],
    ),
    "models/sglang.py": (
        "p2_gateway/5_adapter/2_sglang_connector.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
            (r"from \.model_interface import ModelInterface", "from p3_state.model_interface import ModelInterface"),
            (r"from \.model_adapter import ModelAdapter", "from models.model_adapter import ModelAdapter"),
        ],
    ),
    "models/vllm.py": (
        "p2_gateway/5_adapter/3_vllm_connector.py",
        [
            (r"from serin\.core\.logger import logger", "from p4_config.logger import logger"),
            (r"from \.model_interface import ModelInterface", "from p3_state.model_interface import ModelInterface"),
            (r"from \.model_adapter import ModelAdapter", "from models.model_adapter import ModelAdapter"),
        ],
    ),
}

# Redirect shims for OLD source locations that redirect to new p2_gateway locations
SHIM_REDIRECTS = {
    "serin/messaging/mention_translator.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.1_discord.2_mention_translator import MentionTranslator\n'
    ),
    "serin/messaging/crawler.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.1_discord.2a_message_crawler import MessageCrawler\n'
    ),
    "serin/utils/passive_monitor.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.1_discord.3_passive_monitor import PassiveMonitor\n'
    ),
    "voice/tracker.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.1_discord.4_voice_tracker import VoiceTracker\n'
    ),
    "tts/tts_engine.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.2_voice.1_tts_engine import TTSEngine\n'
    ),
    "voice/profiles.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.2_voice.1a_voice_profiles import (\n'
        '    VoiceProfile, VoiceProfileManager, get_profile_manager,\n'
        '    get_voice_profiles, get_active_profile_name, create_profile,\n'
        '    set_active_profile, delete_profile\n'
        ')\n'
    ),
    "voice/bridge.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.2_voice.2_rust_voice_bridge import RustVoiceBridge, RustStdoutReader\n'
    ),
    "voice/listener.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.2_voice.2a_voice_listener import VoiceListener, InfoCaptureProtocol\n'
    ),
    "voice/processor.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.2_voice.3_audio_processor import AudioStreamProcessor\n'
    ),
    "voice/transcriber.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.2_voice.3a_whisper_transcriber import WhisperTranscriber\n'
    ),
    "voice/output.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.2_voice.3b_voice_output_manager import VoiceOutputManager\n'
    ),
    "tts_voice_manager.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.2_voice.1b_voice_file_manager import TTSVoiceManager\n'
    ),
    "models/lm_studio.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.5_adapter.1_lm_studio_connector import LMStudioConnector\n'
    ),
    "models/sglang.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.5_adapter.2_sglang_connector import SGLangConnector\n'
    ),
    "models/vllm.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        'from p2_gateway.5_adapter.3_vllm_connector import VLLMConnector\n'
    ),
    "discord_bot.py": (
        '"""Redirect — moved to p2_gateway. Update your imports."""\n'
        '# noqa: this is the legacy entry point shim\n'
        'from p2_gateway.1_discord.1_bot_entry import main, client\n'
    ),
}


def apply_import_updates(content, updates):
    for old, new in updates:
        content = re.sub(old, new, content)
    return content


def main():
    os.chdir(ROOT)

    # Step 1: Copy files and apply import updates
    print("=" * 60)
    print("STEP 1: Copying files and updating imports")
    print("=" * 60)
    for src, (dst, updates) in MAPPING.items():
        src_path = os.path.join(ROOT, src)
        dst_path = os.path.join(ROOT, dst)

        if not os.path.exists(src_path):
            print(f"  SKIP (not found): {src}")
            continue

        # Check if source is a redirect shim
        with open(src_path, "r") as f:
            first_line = f.readline().strip()
        if first_line.startswith('"""Redirect'):
            print(f"  SKIP (already shim): {src}")
            continue

        with open(src_path, "r") as f:
            content = f.read()

        if updates:
            content = apply_import_updates(content, updates)

        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, "w") as f:
            f.write(content)
        print(f"  OK: {src} → {dst}")

    # Step 2: Create __init__.py files for package imports
    print()
    print("=" * 60)
    print("STEP 2: Creating __init__.py files")
    print("=" * 60)
    for pkg_dir in ["p2_gateway", "p2_gateway/1_discord", "p2_gateway/2_voice",
                     "p2_gateway/3_text", "p2_gateway/4_media", "p2_gateway/5_adapter"]:
        init_path = os.path.join(ROOT, pkg_dir, "__init__.py")
        if not os.path.exists(init_path):
            with open(init_path, "w") as f:
                f.write("")
            print(f"  Created: {pkg_dir}/__init__.py")

    # Step 3: Create backward-compatibility shims at old locations
    print()
    print("=" * 60)
    print("STEP 3: Creating compatibility shims at old locations")
    print("=" * 60)
    for old_path, shim_content in SHIM_REDIRECTS.items():
        full_old = os.path.join(ROOT, old_path)
        # Don't overwrite if it's already a shim we wrote
        if os.path.exists(full_old):
            with open(full_old, "r") as f:
                existing = f.read()
            if existing.strip() == shim_content.strip():
                print(f"  SKIP (already shimmed): {old_path}")
                continue
            # If it's the real file, back it up first
            backup = full_old + ".bak"
            if not os.path.exists(backup):
                shutil.copy2(full_old, backup)
                print(f"  Backup: {old_path} → {old_path}.bak")
        with open(full_old, "w") as f:
            f.write(shim_content)
        print(f"  Shim: {old_path} → redirects to p2_gateway")

    # Step 4: Verify
    print()
    print("=" * 60)
    print("STEP 4: Verification")
    print("=" * 60)
    for src, (dst, _) in MAPPING.items():
        dst_path = os.path.join(ROOT, dst)
        if os.path.exists(dst_path):
            with open(dst_path, "r") as f:
                content = f.read()
            old_imports = re.findall(r"from serin\.core\.", content)
            remaining_old = [i for i in old_imports if "serin.core" in i]
            if remaining_old:
                print(f"  WARN: {dst} still has serin.core imports: {remaining_old}")
            else:
                print(f"  OK: {dst}")
        else:
            print(f"  MISSING: {dst}")

    print()
    print("Migration complete!")


if __name__ == "__main__":
    main()
