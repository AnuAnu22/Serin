"""
Import integrity — every key module must import without errors.
Catches IndentationError, NameError, wrong import paths at module level.
"""
from __future__ import annotations

import importlib
import pytest

CORE_MODULES = [
    "serin.d1_2_gateway_io.d2_1_discord_bot.bot",
    "serin.d1_2_gateway_io.d2_1_discord_bot.bot_pipeline_init",
    "serin.d1_1_pipeline_flow.d2_1_ingest_stage.d3_2_core_process.manager",
    "serin.d1_5_ops_tooling.background",
    "serin.d1_5_ops_tooling.passive_monitor",
    "serin.d1_1_pipeline_flow.d2_1_ingest_stage.d3_3_sync_load.crawler",
    "serin.d1_1_pipeline_flow.d2_4_remember_stage.d3_1_core_store.store",
    "serin.d1_1_pipeline_flow.d2_4_remember_stage.sync_monitor",
    "serin.d1_3_state_core.d2_4_voice_state.voice_tracker",
    "serin.d1_1_pipeline_flow.d2_3_think_stage.response_controller",
    "serin.d1_1_pipeline_flow.d2_1_ingest_stage.d3_1_context_assembly.mention_translator",
    "serin.d1_3_state_core.d2_1_db_protect",
]

VOICE_MODULES = [
    "serin.d1_2_gateway_io.d2_2_voice_system.d3_1_audio_pipeline.audio_vad",
    "serin.d1_2_gateway_io.d2_2_voice_system.d3_1_audio_pipeline.audio_utils",
    "serin.d1_2_gateway_io.d2_2_voice_system.d3_1_audio_pipeline.audio_transcribe",
    "serin.d1_2_gateway_io.d2_2_voice_system.output",
    "serin.d1_2_gateway_io.d2_2_voice_system.tts_engine",
    "serin.d1_2_gateway_io.d2_2_voice_system.listener",
    "serin.d1_2_gateway_io.d2_2_voice_system.processor",
]


@pytest.mark.parametrize("module_name", CORE_MODULES + VOICE_MODULES)
def test_module_imports_cleanly(module_name: str) -> None:
    importlib.import_module(module_name)


def test_voice_available() -> None:
    from serin.d1_2_gateway_io.d2_1_discord_bot.bot import voice_available
    assert voice_available is True
