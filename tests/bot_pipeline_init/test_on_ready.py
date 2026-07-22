from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _patch_deps() -> None:
    """Mock every import that on_ready() pulls in so it can run in isolation."""
    # Patch modules directly rather than via monkeypatch dotted strings
    import serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator as rg
    import serin.d1_2_gateway_io.d2_4_io_di as gateway_di
    import serin.d1_2_gateway_io.d2_1_io_discord.d3_2_discord_bot as bot_m
    import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init as bpi
    import serin.d1_1_serin_di as root_di

    self = _patch_deps  # type: ignore[attr-defined]
    # Use class-level storage for patches
    # -- Mock logger --
    ml = MagicMock()
    self.mock_logger = ml  # type: ignore[attr-defined]
    gateway_di.get_logger = lambda: ml

    # -- Mock client --
    mc = MagicMock()
    mc.user = MagicMock()
    mc.user.id = 99999
    mc.guilds = []
    self.mock_client = mc  # type: ignore[attr-defined]

    # -- Mock config --
    mcfg = MagicMock()
    mcfg.ALLOWED_CHANNEL_IDS = {12345}
    mcfg.ENABLE_VOICE = False
    mcfg.ENABLE_TTS = False
    mcfg.TRACE_MESSAGES = False
    mcfg.MAINTENANCE_INTERVAL_HOURS = 6
    mcfg.VOICE_RECEIVER_MODE = "opus"
    mcfg.QDRANT_HOST = "localhost"
    mcfg.QDRANT_PORT = 6333
    self.mock_config = mcfg  # type: ignore[attr-defined]

    # Patch all module-level references
    bpi.client = mc
    bpi.config = mcfg
    bot_m.voice_available = False
    bot_m.mention_translator = None

    # Mock DI functions
    root_di.init_root = MagicMock()
    root_di.set_crawler = MagicMock()
    root_di.set_mention_translator = MagicMock()
    root_di.set_message_manager = MagicMock()
    root_di.set_qdrant = MagicMock()

    # Mock LLM
    rg.initialize_llama = AsyncMock()
    rg.llama = MagicMock()
    rg.llama.is_connected = True
    rg.discord_client = None
    rg.get_response_natural = MagicMock()

    # Mock other internal imports
    import serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_1_ingest_context.d4_3_mention_translator as mt
    mt.MentionTranslator = lambda *a, **kw: MagicMock()

    bot_m.init_database_protection = MagicMock()
    bot_m.db_protector = MagicMock()
    bpi.db_protector = MagicMock()

    import serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_3_remember_qdrant as qd
    mock_qd = MagicMock()
    qd.QdrantMemorySystem = lambda *a, **kw: mock_qd

    import serin.d1_5_ops_tooling.d2_2_tooling_background as bg
    mock_bg = MagicMock()
    mock_bg.start = AsyncMock()
    bg.BackgroundProcessor = lambda *a, **kw: mock_bg
    bpi.background_processor = mock_bg
    bot_m.background_processor = mock_bg

    import serin.d1_5_ops_tooling.d2_4_passive_monitor as pm
    mock_pm = MagicMock()
    pm.PassiveMonitor = lambda *a, **kw: mock_pm

    import serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_3_ingest_sync.d4_2_sync_crawler as cr
    mock_crawler = MagicMock()
    mock_crawler.start = AsyncMock()
    cr.MessageCrawler = lambda *a, **kw: mock_crawler
    bpi.message_crawler = mock_crawler
    bot_m.message_crawler = mock_crawler

    import serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_4_sync_monitor as sm
    mock_sync = MagicMock()
    mock_sync.start_monitoring = AsyncMock()
    sm.MemorySyncMonitor = lambda *a, **kw: mock_sync

    import serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_4_core_manager as mgr
    mock_mm = MagicMock()
    mock_mm.response_controller = MagicMock()
    mock_mm.context_builder = MagicMock()
    mock_mm.bot_personality = MagicMock()
    mock_mm.enhanced_context = MagicMock()
    mock_mm.personality = MagicMock()
    mock_mm.voice_tracker = MagicMock()
    mgr.EnhancedMessageManagerV3 = lambda *a, **kw: mock_mm
    bpi.message_manager = mock_mm

    import serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline as pl
    mock_pipeline = MagicMock()
    pl.MessagePipeline.build = MagicMock(return_value=mock_pipeline)

    import serin.d1_3_state_core.d2_5_thinking_filter as tf
    tf.get_thinking_filter = MagicMock(return_value=MagicMock())

    import serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server as cps
    cps.broadcast_event = MagicMock()
    cps.bot_state = {}

    import serin.d1_5_ops_tooling.d2_1_control_panel.d3_3_panel_lifecycle as cpl
    cpl.start_server = AsyncMock()
    cpl.init_bot_state = MagicMock()

    bpi.asyncio.to_thread = AsyncMock(return_value=None)
    bpi.asyncio.create_task = lambda coro: MagicMock()


class TestOnReady:
    async def test_ready_completes_successfully(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_ready

        await on_ready()

    async def test_ready_logs_separator_lines(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_ready

        logger = _patch_deps.mock_logger  # type: ignore[attr-defined]
        await on_ready()

        sep = "=" * 60
        logger.success.assert_any_call(sep)

    async def test_ready_logs_final_message(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_ready

        logger = _patch_deps.mock_logger  # type: ignore[attr-defined]
        await on_ready()

        actual_msg = f"Serin fully initialized \u2014 listening on {len(_patch_deps.mock_client.guilds)} guild(s)"  # type: ignore[attr-defined]
        logger.success.assert_any_call(actual_msg)

    async def test_ready_initializes_memory_system(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_ready

        await on_ready()

        import serin.d1_1_serin_di as root_di
        root_di.set_qdrant.assert_called_once()
