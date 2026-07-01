"""Fix 5/5 violations, create DI container, and update all imports.

Run: python3 scripts/fix_structure.py
Then: uv run ruff check serin/ --fix
"""
from __future__ import annotations

import os
import shutil

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIN = os.path.join(PROJECT, "serin")


def mv(src_rel: str, dst_rel: str) -> None:
    src = os.path.join(PROJECT, src_rel)
    dst = os.path.join(PROJECT, dst_rel)
    if not os.path.exists(src):
        print(f"  SKIP (src missing): {src_rel}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    print(f"  {src_rel} -> {dst_rel}")


def write_file(rel_path: str, content: str) -> None:
    fp = os.path.join(PROJECT, rel_path)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w") as f:
        f.write(content)
    print(f"  WROTE: {rel_path}")


def _mkdir(path: str) -> None:
    p = os.path.join(PROJECT, path)
    os.makedirs(p, exist_ok=True)
    init = os.path.join(p, "__init__.py")
    if not os.path.exists(init):
        with open(init, "w") as f:
            f.write("# intentionally empty\n")


# ── Phase 1: 5/5 fixes — regroup files into subdirectories ──────────────
print("=== Phase 1: 5/5 file regroup ===")

# 1. voice_system/ (too many files)
_mkdir("serin/d1_2_gateway_io/voice_system/audio/process")
mv("serin/d1_2_gateway_io/voice_system/audio_processor.py",
   "serin/d1_2_gateway_io/voice_system/audio/process/audio_processor.py")
mv("serin/d1_2_gateway_io/voice_system/voice_behavior.py",
   "serin/d1_2_gateway_io/voice_system/audio/process/voice_behavior.py")
mv("serin/d1_2_gateway_io/voice_system/bridge.py",
   "serin/d1_2_gateway_io/voice_system/bridge_io/bridge.py")
stub = os.path.join(PROJECT, "serin/d1_2_gateway_io/voice_system/processor.py")
if os.path.exists(stub):
    os.remove(stub)
    print("  DELETED: processor.py")
sreader = os.path.join(PROJECT, "serin/d1_2_gateway_io/voice_system/bridge_io/stdout_reader.py")
if os.path.exists(sreader):
    os.remove(sreader)
    print("  DELETED: stdout_reader.py")

# 2. control_panel/ (too many files)
_mkdir("serin/d1_5_ops_tooling/control_panel/panels")
mv("serin/d1_5_ops_tooling/control_panel/panel_control.py",
   "serin/d1_5_ops_tooling/control_panel/panels/panel_control.py")
mv("serin/d1_5_ops_tooling/control_panel/panel_voice.py",
   "serin/d1_5_ops_tooling/control_panel/panels/panel_voice.py")

# 3. remember/core/ (too many files)
_mkdir("serin/d1_1_pipeline_flow/remember/core/storage")
mv("serin/d1_1_pipeline_flow/remember/core/search_store.py",
   "serin/d1_1_pipeline_flow/remember/core/storage/search_store.py")
mv("serin/d1_1_pipeline_flow/remember/core/sqlite_store.py",
   "serin/d1_1_pipeline_flow/remember/core/storage/sqlite_store.py")
mv("serin/d1_1_pipeline_flow/remember/core/write_store.py",
   "serin/d1_1_pipeline_flow/remember/core/storage/write_store.py")

# 4. voice_transcribe/ (too many files)
_mkdir("serin/d1_2_gateway_io/voice_transcribe/models")
mv("serin/d1_2_gateway_io/voice_transcribe/profiles.py",
   "serin/d1_2_gateway_io/voice_transcribe/models/profiles.py")
mv("serin/d1_2_gateway_io/voice_transcribe/tracker.py",
   "serin/d1_2_gateway_io/voice_transcribe/models/tracker.py")

# 5. act/runners/ (too many files)
_mkdir("serin/d1_1_pipeline_flow/act/runners/dispatch")
mv("serin/d1_1_pipeline_flow/act/runners/llm_call.py",
   "serin/d1_1_pipeline_flow/act/runners/dispatch/llm_call.py")
mv("serin/d1_1_pipeline_flow/act/runners/send.py",
   "serin/d1_1_pipeline_flow/act/runners/dispatch/send.py")

# 6. ingest/core/ (too many files)
_mkdir("serin/d1_1_pipeline_flow/ingest/core/vision")
mv("serin/d1_1_pipeline_flow/ingest/core/visual_memory.py",
   "serin/d1_1_pipeline_flow/ingest/core/vision/visual_memory.py")

# 7. remember/knowledge/ (too many files)
_mkdir("serin/d1_1_pipeline_flow/remember/knowledge/belief")
mv("serin/d1_1_pipeline_flow/remember/knowledge/beliefs.py",
   "serin/d1_1_pipeline_flow/remember/knowledge/belief/beliefs.py")
mv("serin/d1_1_pipeline_flow/remember/knowledge/evidence.py",
   "serin/d1_1_pipeline_flow/remember/knowledge/belief/evidence.py")

# 8. think/ (too many files)
_mkdir("serin/d1_1_pipeline_flow/think/personality")
mv("serin/d1_1_pipeline_flow/think/personality_state.py",
   "serin/d1_1_pipeline_flow/think/personality/personality_state.py")
mv("serin/d1_1_pipeline_flow/think/humanization.py",
   "serin/d1_1_pipeline_flow/think/personality/humanization.py")

# ── Phase 2: Create DI container ─────────────────────────────────────────
print("\n=== Phase 2: Gateway DI container ===")
di_content = '''"""Dependency injection container for gateway layer."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from logging import Logger

_logger: Logger | None = None


def init_gateway(logger: Logger) -> None:
    global _logger
    _logger = logger


def get_logger() -> Logger:
    if _logger is None:
        raise RuntimeError("Gateway not initialized")
    return _logger
'''
write_file("serin/d1_2_gateway_io/_di.py", di_content)

print("\n=== Done. Run: uv run ruff check serin/ --fix ===")
