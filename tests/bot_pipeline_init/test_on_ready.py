from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _patch_deps() -> None:
    """Mock on_ready's dependencies so it runs in isolation.

    Post-refactor on_ready only constructs a PipelineInitializer, awaits its
    initialize(), and re-exports the resulting subsystem singletons onto the
    module globals. The heavy per-subsystem wiring (and its logging) now lives
    inside PipelineInitializer, so we mock that class here.
    """
    import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init as bpi
    import serin.d1_2_gateway_io.d2_4_io_di as gateway_di

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
    bpi.client = mc

    # -- Mock bot_state --
    bpi.bot_state = {}

    # -- Mock PipelineInitializer --
    mock_init = MagicMock()
    mock_init.initialize = AsyncMock()
    mock_init.message_manager = MagicMock()
    mock_init.voice_behavior_manager = MagicMock()
    mock_init.voice_listener = MagicMock()
    self.mock_initializer = mock_init  # type: ignore[attr-defined]
    # on_ready references the name `PipelineInitializer` bound in the package
    # namespace (imported from d4_1_pipeline_initializer at module load).
    bpi.PipelineInitializer = MagicMock(return_value=mock_init)


class TestOnReady:
    async def test_ready_completes_successfully(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_ready

        await on_ready()

        _patch_deps.mock_initializer.initialize.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_ready_builds_initializer_with_client_and_state(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init as bpi
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_ready

        await on_ready()

        bpi.PipelineInitializer.assert_called_once_with(  # type: ignore[attr-defined]
            _patch_deps.mock_client, {}  # type: ignore[attr-defined]
        )

    async def test_ready_re_exports_subsystem_singletons(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init as bpi
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_ready

        await on_ready()

        init = _patch_deps.mock_initializer  # type: ignore[attr-defined]
        assert bpi.message_manager is init.message_manager
        assert bpi.voice_behavior_manager is init.voice_behavior_manager
        assert bpi.voice_listener is init.voice_listener

    async def test_ready_awaits_submodule_initialization(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_ready

        await on_ready()

        _patch_deps.mock_initializer.initialize.assert_awaited_once()  # type: ignore[attr-defined]
