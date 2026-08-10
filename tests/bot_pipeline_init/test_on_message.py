from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest


def _text_channel(**overrides: Any) -> MagicMock:
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = 12345
    ch.name = "general"
    ch.send = AsyncMock()
    for k, v in overrides.items():
        setattr(ch, k, v)
    return ch


class TestOnMessage:
    """Unit tests for on_message filter and dispatch logic."""

    @pytest.fixture(autouse=True)
    def _patch_bpi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch module-level dependencies *after* import so on_message runs in isolation."""
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init as bpi

        # Patch client
        self.mock_client: Any = MagicMock(spec=["user", "event", "guilds"])
        self.mock_client.user = MagicMock()
        self.mock_client.user.id = 99999
        monkeypatch.setattr(bpi, "client", self.mock_client)

        # Patch subsystem globals via _initializer (on_message reads _initializer.<attr>)
        self.mock_mm: Any = AsyncMock()
        self.mock_pm: Any = AsyncMock()

        self.mock_initializer: Any = MagicMock()
        self.mock_initializer.message_manager = self.mock_mm
        self.mock_initializer.passive_monitor = self.mock_pm
        self.mock_initializer.background_processor = AsyncMock()
        self.mock_initializer.message_crawler = AsyncMock()
        monkeypatch.setattr(bpi, "_initializer", self.mock_initializer)

        self.mock_stats: dict[str, int] = {
            "messages_received": 0,
            "messages_processed": 0,
            "passive_messages": 0,
            "errors": 0,
        }
        monkeypatch.setattr(bpi, "stats", self.mock_stats)

        self.mock_profile_cmd: Any = AsyncMock(return_value=False)
        self.mock_stats_cmd: Any = AsyncMock(return_value=False)
        self.mock_help_cmd: Any = AsyncMock(return_value=False)
        monkeypatch.setattr(bpi, "handle_profile_command", self.mock_profile_cmd)
        monkeypatch.setattr(bpi, "handle_stats_command", self.mock_stats_cmd)
        monkeypatch.setattr(bpi, "handle_help_command", self.mock_help_cmd)

        # Patch config so is_allowed_channel / trace checks are deterministic
        self.mock_bpi_config: Any = MagicMock()
        self.mock_bpi_config.ALLOWED_CHANNEL_IDS = {12345}
        self.mock_bpi_config.TRACE_MESSAGES = False
        monkeypatch.setattr(bpi, "config", self.mock_bpi_config)

    def _msg(self, **overrides: Any) -> MagicMock:
        msg = MagicMock()
        msg.author = MagicMock()
        msg.author.id = 11111
        msg.author.display_name = "TestUser"
        msg.channel = _text_channel()
        msg.guild = MagicMock()
        msg.guild.id = 22222
        msg.guild.name = "TestGuild"
        msg.content = "hello world"
        msg.attachments = []
        for k, v in overrides.items():
            setattr(msg, k, v)
        return msg

    # ----------------------------------------------------------------
    # Filter 1: Ignore bot's own messages
    # ----------------------------------------------------------------
    async def test_ignores_bot_own_message(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg()
        msg.author = self.mock_client.user

        await on_message(msg)

        assert self.mock_stats["messages_processed"] == 0

    # ----------------------------------------------------------------
    # Filter 2: Only text channels
    # ----------------------------------------------------------------
    async def test_ignores_non_text_channel(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg()
        msg.channel = MagicMock(spec=discord.VoiceChannel)

        await on_message(msg)

        assert self.mock_stats["messages_received"] == 1
        assert self.mock_stats["messages_processed"] == 0

    async def test_ignores_dm_channel(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg()
        msg.channel = MagicMock(spec=discord.DMChannel)

        await on_message(msg)

        assert self.mock_stats["messages_processed"] == 0

    # ----------------------------------------------------------------
    # Filter 3: Empty message without attachments
    # ----------------------------------------------------------------
    async def test_ignores_empty_message_no_attachments(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg(content="  ", attachments=[])

        await on_message(msg)

        assert self.mock_stats["messages_received"] == 1
        assert self.mock_stats["messages_processed"] == 0

    async def test_empty_with_attachments_is_processed(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg(content="", attachments=[MagicMock()])

        await on_message(msg)

        assert self.mock_stats["messages_received"] == 1
        assert self.mock_stats["messages_processed"] == 1

    async def test_non_empty_message_without_attachments_is_processed(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg(content="hello", attachments=[])

        await on_message(msg)

        assert self.mock_stats["messages_received"] == 1
        assert self.mock_stats["messages_processed"] == 1

    # ----------------------------------------------------------------
    # Channel filtering — allowed vs non-allowed
    # ----------------------------------------------------------------
    async def test_passes_non_allowed_channel_to_passive_only(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        self.mock_bpi_config.ALLOWED_CHANNEL_IDS = {99999}

        msg = self._msg()

        await on_message(msg)

        assert self.mock_stats["passive_messages"] == 1
        assert self.mock_stats["messages_processed"] == 0
        self.mock_pm.process_message.assert_awaited_once()

    async def test_passive_monitor_called_for_allowed_channel(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg()
        await on_message(msg)

        self.mock_pm.process_message.assert_awaited_once_with(msg, True)

    async def test_passive_monitor_called_for_non_allowed_channel(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        self.mock_bpi_config.ALLOWED_CHANNEL_IDS = {99999}
        msg = self._msg()

        await on_message(msg)

        self.mock_pm.process_message.assert_awaited_once_with(msg, False)

    async def test_skips_passive_when_monitor_is_none(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        self.mock_initializer.passive_monitor = None
        msg = self._msg()

        await on_message(msg)

        assert self.mock_stats["messages_processed"] == 1

    # ----------------------------------------------------------------
    # Command handler dispatch
    # ----------------------------------------------------------------
    async def test_calls_profile_command_handler(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg()
        await on_message(msg)

        self.mock_profile_cmd.assert_awaited_once()

    async def test_calls_stats_command_handler(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg()
        await on_message(msg)

        self.mock_stats_cmd.assert_awaited_once()

    async def test_calls_help_command_handler(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg()
        await on_message(msg)

        self.mock_help_cmd.assert_awaited_once()

    async def test_stops_on_profile_command(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init as bpi
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        bpi.handle_profile_command = AsyncMock(return_value=True)
        msg = self._msg()

        await on_message(msg)

        self.mock_stats_cmd.assert_not_awaited()
        self.mock_mm.process_message.assert_not_awaited()

    async def test_stops_on_stats_command(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init as bpi
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        bpi.handle_stats_command = AsyncMock(return_value=True)
        msg = self._msg()

        await on_message(msg)

        self.mock_help_cmd.assert_not_awaited()
        self.mock_mm.process_message.assert_not_awaited()

    async def test_stops_on_help_command(self) -> None:
        import serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init as bpi
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        bpi.handle_help_command = AsyncMock(return_value=True)
        msg = self._msg()

        await on_message(msg)

        self.mock_mm.process_message.assert_not_awaited()

    # ----------------------------------------------------------------
    # Message manager dispatch
    # ----------------------------------------------------------------
    async def test_dispatches_to_manager(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        msg = self._msg()
        await on_message(msg)

        self.mock_mm.process_message.assert_awaited_once_with(msg)

    async def test_manager_none_errors(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        self.mock_initializer.message_manager = None
        msg = self._msg()

        await on_message(msg)

        assert self.mock_stats["errors"] == 1

    # ----------------------------------------------------------------
    # Error handling
    # ----------------------------------------------------------------
    async def test_exception_increments_error_stat(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        self.mock_mm.process_message = AsyncMock(side_effect=RuntimeError("boom"))
        msg = self._msg()

        await on_message(msg)

        assert self.mock_stats["errors"] == 1

    async def test_exception_in_passive_monitor_does_not_crash(self) -> None:
        from serin.d1_2_gateway_io.d2_1_io_discord.d3_1_pipeline_init import on_message

        self.mock_pm.process_message = AsyncMock(side_effect=RuntimeError("boom"))
        msg = self._msg()

        await on_message(msg)

        assert self.mock_stats["errors"] == 1
        assert self.mock_stats["messages_processed"] == 0
