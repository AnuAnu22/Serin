"""
Import integrity — every key module must import without errors.
Catches IndentationError, NameError, wrong import paths at module level.
"""
from __future__ import annotations

import importlib
import pytest

CORE_MODULES = [
    "serin.gateway.discord.bot",
    "serin.gateway.discord.bot_pipeline_init",
    "serin.pipeline.ingest.core.manager",
    "serin.ops.background",
    "serin.ops.passive_monitor",
    "serin.pipeline.ingest.sync.crawler",
    "serin.pipeline.remember.core.store",
    "serin.pipeline.remember.sync_monitor",
    "serin.state.voice.voice_tracker",
    "serin.pipeline.think.response_controller",
    "serin.pipeline.ingest.context.mention_translator",
    "serin.state.db_protect",
]

VOICE_MODULES = [
    "serin.gateway.voice_system.audio.audio_vad",
    "serin.gateway.voice_system.audio.audio_utils",
    "serin.gateway.voice_system.audio.audio_transcribe",
    "serin.gateway.voice_system.output",
    "serin.gateway.voice_system.tts_engine",
    "serin.gateway.voice_system.listener",
    "serin.gateway.voice_system.processor",
]


@pytest.mark.parametrize("module_name", CORE_MODULES + VOICE_MODULES)
def test_module_imports_cleanly(module_name: str) -> None:
    importlib.import_module(module_name)


def test_voice_available() -> None:
    from serin.gateway.discord.bot import voice_available
    assert voice_available is True
