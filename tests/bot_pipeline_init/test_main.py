from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import discord
import pytest


class TestMain:
    """Unit tests for main() — retry logic, exception handlers, and init flow."""

    @pytest.fixture(autouse=True)
    def _patch_main(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        # Mock discord client
        self.mock_client: Any = MagicMock()
        self.mock_client.is_closed = MagicMock(return_value=False)
        self.mock_client.close = AsyncMock()
        self.mock_client.start = AsyncMock()
        monkeypatch.setattr(me, "client", self.mock_client)

        # Mock logger
        self.mock_logger: Any = MagicMock()
        monkeypatch.setattr(me, "get_logger", lambda: self.mock_logger)

        # Mock config
        self.mock_config: Any = MagicMock()
        self.mock_config.DEBUG_MODE = False
        self.mock_config.TRACE_MESSAGES = False
        self.mock_config.ALLOWED_CHANNEL_IDS = {12345}
        self.mock_config.MAINTENANCE_INTERVAL_HOURS = 6
        self.mock_config.ENABLE_VOICE = True
        self.mock_config.ENABLE_TTS = False
        self.mock_config.DISCORD_TOKEN = "fake-token-mock"
        self.mock_config.CONTROL_PANEL_PORT = 9999
        monkeypatch.setattr(me, "config", self.mock_config)

        # Mock response_generator.discord_client setter
        monkeypatch.setattr(
            "serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator.discord_client",
            None,
        )

        # Mock event_handlers.run_maintenance (patched on the actual module object)
        self.mock_run_maintenance: Any = AsyncMock()
        monkeypatch.setattr(me.event_handlers, "run_maintenance", self.mock_run_maintenance)

        # Mock asyncio.sleep so retry backoff doesn't block tests
        monkeypatch.setattr(me.asyncio, "sleep", AsyncMock())

    # ----------------------------------------------------------------
    # Success paths
    # ----------------------------------------------------------------
    async def test_main_success_first_attempt(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        await me.main()

        self.mock_client.start.assert_awaited_once_with("fake-token-mock")
        self.mock_client.close.assert_awaited_once()
        self.mock_run_maintenance.assert_called_once()

    async def test_main_logs_banner_and_config_on_success(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        await me.main()

        # Verify separator lines use correct operator
        sep = "=" * 60
        self.mock_logger.info.assert_any_call(sep)

        # Verify configuration logging
        self.mock_logger.info.assert_any_call(
            f"   Trace messages: {self.mock_config.TRACE_MESSAGES}"
        )
        self.mock_logger.info.assert_any_call(
            f"   Response channels: {len(self.mock_config.ALLOWED_CHANNEL_IDS)}"
        )
        self.mock_logger.info.assert_any_call(
            f"   Maintenance interval: {self.mock_config.MAINTENANCE_INTERVAL_HOURS}h"
        )
        self.mock_logger.info.assert_any_call(
            f"   Voice tracking: {self.mock_config.ENABLE_VOICE}"
        )

    # ----------------------------------------------------------------
    # Debug mode
    # ----------------------------------------------------------------
    async def test_main_debug_mode_logs(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_config.DEBUG_MODE = True
        await me.main()

        self.mock_logger.info.assert_any_call(
            "Debug mode enabled - verbose logging active"
        )

    async def test_main_debug_mode_off_does_not_log(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_config.DEBUG_MODE = False
        await me.main()

        debug_calls = [
            call
            for call in self.mock_logger.info.call_args_list
            if "Debug mode enabled" in str(call)
        ]
        assert len(debug_calls) == 0

    # ----------------------------------------------------------------
    # Retry logic — succeeds after failures
    # ----------------------------------------------------------------
    async def test_main_retries_on_client_error(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.start = AsyncMock(
            side_effect=[
                aiohttp.ClientError("conn reset"),
                aiohttp.ClientError("timeout"),
                None,
            ]
        )

        await me.main()

        assert self.mock_client.start.await_count == 3
        self.mock_client.close.assert_awaited_once()
        assert self.mock_run_maintenance.call_count == 3  # once per attempt

    async def test_main_retries_on_connection_closed(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.start = AsyncMock(
            side_effect=[
                discord.ConnectionClosed(MagicMock(), shard_id=1),
                None,
            ]
        )

        await me.main()

        assert self.mock_client.start.await_count == 2

    async def test_main_retries_on_gateway_not_found(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.start = AsyncMock(
            side_effect=[
                discord.GatewayNotFound(),
                None,
            ]
        )

        await me.main()

        assert self.mock_client.start.await_count == 2

    async def test_main_retry_logs_wait_time(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.start = AsyncMock(
            side_effect=[
                aiohttp.ClientError("attempt 1"),
                aiohttp.ClientError("attempt 2"),
                None,
            ]
        )

        await me.main()

        # wait_time for retry_count=1: min(30, 2**1) = 2
        self.mock_logger.info.assert_any_call("Retrying in 2 seconds...")
        # wait_time for retry_count=2: min(30, 2**2) = 4
        self.mock_logger.info.assert_any_call("Retrying in 4 seconds...")

    async def test_main_retry_logs_with_max_retries_in_message(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.start = AsyncMock(
            side_effect=[
                aiohttp.ClientError("fail"),
                None,
            ]
        )

        await me.main()

        # "Attempt 1/5", "Attempt 2/5" — assert max_retries=5
        self.mock_logger.info.assert_any_call("Connecting to Discord (Attempt 1/5)...")
        self.mock_logger.info.assert_any_call("Connecting to Discord (Attempt 2/5)...")

    # ----------------------------------------------------------------
    # Retry exhaustion
    # ----------------------------------------------------------------
    async def test_main_raises_after_max_retries(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.start = AsyncMock(
            side_effect=aiohttp.ClientError("persistent failure")
        )

        await me.main()

        # outer except Exception catches the raise from exhausted retries
        assert self.mock_client.start.await_count == 5
        self.mock_client.close.assert_awaited_once()
        self.mock_logger.error.assert_any_call(
            "Failed to connect after 5 attempts: persistent failure"
        )

    async def test_main_exactly_five_attempts_logged(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.start = AsyncMock(
            side_effect=aiohttp.ClientError("no")
        )

        await me.main()

        connect_logs = [
            str(call)
            for call in self.mock_logger.info.call_args_list
            if "Connecting to Discord" in str(call)
        ]
        assert len(connect_logs) == 5

    # ----------------------------------------------------------------
    # Outer exception handlers
    # ----------------------------------------------------------------
    async def test_main_handles_keyboard_interrupt(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.start = AsyncMock(
            side_effect=KeyboardInterrupt()
        )

        await me.main()

        self.mock_logger.info.assert_any_call(
            "Received keyboard interrupt (Ctrl+C)"
        )

    async def test_main_handles_database_validation_error(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        from serin.d1_3_state_core.d2_1_db_protect import DatabaseValidationError

        self.mock_client.start = AsyncMock(
            side_effect=DatabaseValidationError("schema mismatch")
        )

        await me.main()

        self.mock_logger.error.assert_any_call(
            "Database validation failed: schema mismatch"
        )
        self.mock_logger.error.assert_any_call("Manual intervention required")

    async def test_main_handles_database_recovery_error(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        from serin.d1_3_state_core.d2_1_db_protect import DatabaseRecoveryError

        self.mock_client.start = AsyncMock(
            side_effect=DatabaseRecoveryError("corrupt backup")
        )

        await me.main()

        self.mock_logger.error.assert_any_call(
            "Database recovery failed: corrupt backup"
        )
        self.mock_logger.error.assert_any_call(
            "Try restoring from backup manually"
        )

    async def test_main_handles_generic_exception(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.start = AsyncMock(
            side_effect=ValueError("something unexpected")
        )

        await me.main()

        self.mock_logger.exception.assert_any_call(
            "Fatal error in main: something unexpected"
        )

    # ----------------------------------------------------------------
    # Finally block — client cleanup
    # ----------------------------------------------------------------
    async def test_main_closes_client_when_not_closed(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.is_closed = MagicMock(return_value=False)
        self.mock_client.start = AsyncMock()

        await me.main()

        self.mock_client.is_closed.assert_called_once()
        self.mock_client.close.assert_awaited_once()

    async def test_main_skips_close_when_already_closed(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        self.mock_client.is_closed = MagicMock(return_value=True)

        await me.main()

        self.mock_client.close.assert_not_awaited()

    async def test_main_logs_shutdown_in_finally(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init.d4_1_main_entry as me

        await me.main()

        self.mock_logger.info.assert_any_call("Bot shutdown complete")
