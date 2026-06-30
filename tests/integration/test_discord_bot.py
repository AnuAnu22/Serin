"""
Integration tests for discord_bot.py — message handling flow and event wiring.

Tests the on_message filter chain, command dispatch, and the main() connection
retry logic using mocked discord.py objects.

These tests do NOT connect to Discord — all discord.py objects are mocked.
Voice modules are pre-mocked at sys.modules level to avoid the
MissingVoiceDependenciesError at import time.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import discord
import pytest


# =========================================================================
# Prevent voice module imports from triggering MissingVoiceDependenciesError
# =========================================================================

_FAKE_VOICE_MODULES = {
    "voice.listener": MagicMock(VoiceListener=MagicMock),
    "voice.processor": MagicMock(AudioStreamProcessor=MagicMock),
    "voice.transcriber": MagicMock(WhisperTranscriber=MagicMock),
    "voice.pipeline": MagicMock(VoiceMemoryPipeline=MagicMock),
    "voice.output": MagicMock(VoiceOutputManager=MagicMock),
    "voice.behavior": MagicMock(VoiceBehaviorManager=MagicMock),
    # The voice/__init__.py also imports from listener — provide that too
    "voice": MagicMock(),
}

for _mod_name, _mod_obj in _FAKE_VOICE_MODULES.items():
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _mod_obj


# =========================================================================
# Helpers
# =========================================================================


def _make_mock_message(**kwargs) -> MagicMock:
    """Create a minimal mock discord.Message with configurable attributes."""
    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock(spec=discord.User)
    msg.author.id = 12345
    msg.author.display_name = "TestUser"
    msg.author.bot = False
    # Use spec from a real TextChannel so isinstance check passes
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = 99999
    msg.channel.name = "test-channel"
    msg.channel.send = AsyncMock()
    msg.content = kwargs.pop("content", "hello")
    msg.attachments = kwargs.pop("attachments", [])
    msg.mentions = kwargs.pop("mentions", [])
    msg.guild = MagicMock()
    msg.guild.id = 11111
    for key, value in kwargs.items():
        setattr(msg, key, value)
    return msg


# We patch discord_bot's module-level attributes before each test.
# The imports are deferred so patches take effect before the module globals are accessed.
@pytest.fixture(autouse=True)
def _patch_discord_bot_globals():
    """Patch discord_bot's module-level globals to prevent real Discord connections."""
    patcher = patch.multiple(
        "discord_bot",
        client=MagicMock(),
        mention_translator=MagicMock(),
        message_manager=AsyncMock(),
        background_processor=AsyncMock(),
        passive_monitor=AsyncMock(),
        message_crawler=AsyncMock(),
        voice_listener=None,
        audio_processor=None,
        voice_pipeline=None,
        tts_engine=None,
        voice_output_manager=None,
        voice_manager=None,
        voice_behavior_manager=None,
        config=MagicMock(),
        stats={
            "messages_received": 0,
            "messages_processed": 0,
            "messages_ignored": 0,
            "passive_messages": 0,
            "commands_executed": 0,
            "corrections_detected": 0,
            "voice_events": 0,
            "voice_messages": 0,
            "errors": 0,
            "start_time": None,
        },
    )
    with patcher:
        yield


class TestOnMessageFilterChain:
    """Tests for the on_message event handler's early-return filters."""

    @pytest.mark.asyncio
    async def test_ignores_bot_own_message(self):
        """Message from client.user is filtered out before processing."""
        import discord_bot

        msg = _make_mock_message(content="test")
        msg.author = discord_bot.client.user  # same as bot

        await discord_bot.on_message(msg)

        # passive_monitor should NOT be called
        discord_bot.passive_monitor.process_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_non_text_channel(self):
        """Message in a DM or non-text channel is filtered out."""
        import discord_bot

        msg = _make_mock_message(content="test")
        msg.channel = MagicMock(spec=discord.DMChannel)

        await discord_bot.on_message(msg)

        discord_bot.passive_monitor.process_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_empty_message_without_attachments(self):
        """Empty message with no attachments is filtered out."""
        import discord_bot

        msg = _make_mock_message(content="")
        msg.attachments = []

        await discord_bot.on_message(msg)

        discord_bot.passive_monitor.process_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_message_with_attachment_even_if_empty_content(self):
        """Empty message WITH an attachment should pass the filter."""
        import discord_bot

        discord_bot.config.ALLOWED_CHANNEL_IDS = {99999}

        msg = _make_mock_message(content="")
        msg.attachments = [MagicMock()]

        await discord_bot.on_message(msg)

        discord_bot.passive_monitor.process_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_non_empty_message(self):
        """Message with content passes the empty-message filter."""
        import discord_bot

        discord_bot.config.ALLOWED_CHANNEL_IDS = {99999}

        msg = _make_mock_message(content="hello world")

        await discord_bot.on_message(msg)

        discord_bot.passive_monitor.process_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_non_allowed_channel_passively(self):
        """Message in non-allowed channel goes to passive_monitor but returns early."""
        import discord_bot

        discord_bot.config.ALLOWED_CHANNEL_IDS = {88888}  # not 99999

        msg = _make_mock_message(content="hello")
        msg.channel.id = 99999

        await discord_bot.on_message(msg)

        # passive_monitor should be called
        discord_bot.passive_monitor.process_message.assert_awaited_once()
        # message_manager should NOT be called (only passive monitoring)
        discord_bot.message_manager.process_message.assert_not_called()


class TestCommandDispatch:
    """Tests for the !profile, !stats, !help command handlers."""

    @pytest.mark.asyncio
    async def test_help_command_sends_response(self):
        """!help sends the help text and returns."""
        import discord_bot

        discord_bot.config.ALLOWED_CHANNEL_IDS = {99999}

        msg = _make_mock_message(content="!help")
        msg.channel.id = 99999

        await discord_bot.on_message(msg)

        msg.channel.send.assert_awaited_once()
        response_text = msg.channel.send.call_args[0][0]
        assert "**Serin Bot Commands**" in response_text

    @pytest.mark.asyncio
    async def test_profile_command_dispatches(self):
        """!profile calls message_manager.get_user_profile."""
        import discord_bot

        discord_bot.config.ALLOWED_CHANNEL_IDS = {99999}
        discord_bot.message_manager.get_user_profile = MagicMock(return_value={
            "personality_traits": ["curious", "helpful"],
            "interests": ["AI", "music"],
            "total_messages": 42,
            "avg_message_length": 120.5,
            "last_seen": "2026-06-30",
        })

        msg = _make_mock_message(content="!profile")
        msg.channel.id = 99999

        await discord_bot.on_message(msg)

        discord_bot.message_manager.get_user_profile.assert_called_once()
        msg.channel.send.assert_awaited_once()
        response_text = msg.channel.send.call_args[0][0]
        assert "**Profile: TestUser**" in response_text

    @pytest.mark.asyncio
    async def test_stats_command_dispatches(self):
        """!stats calls message_manager.get_memory_stats."""
        import discord_bot

        discord_bot.config.ALLOWED_CHANNEL_IDS = {99999}
        discord_bot.message_manager.get_memory_stats = MagicMock(return_value={
            "total_memories": 1000,
            "total_users": 50,
            "strong_relationships": 10,
            "manager_stats": {"responses_generated": 500, "corrections_detected": 25},
        })
        discord_bot.message_manager.voice_tracker = MagicMock()
        discord_bot.message_manager.voice_tracker.get_stats = MagicMock(return_value={
            "users_in_voice": 3,
            "active_sessions": 2,
        })
        discord_bot.stats["start_time"] = 0.0  # reference for uptime calc
        discord_bot.background_processor.get_stats = MagicMock(return_value={
            "queue_size": 5, "summaries_created": 10, "total_processed": 100,
        })
        discord_bot.passive_monitor.get_stats = MagicMock(return_value={
            "servers_monitored": 2, "channels_monitored": 10,
        })
        discord_bot.message_crawler.get_stats = MagicMock(return_value={
            "quick_syncs": 50, "deep_validations": 10, "messages_backfilled": 200, "gaps_found": 2,
        })

        msg = _make_mock_message(content="!stats")
        msg.channel.id = 99999

        await discord_bot.on_message(msg)

        msg.channel.send.assert_awaited_once()
        response_text = msg.channel.send.call_args[0][0]
        assert "**Bot Statistics**" in response_text
        assert "Total Memories: 1000" in response_text


class TestMainRetryLogic:
    """Tests for the main() async function's connection retry loop."""

    @pytest.fixture(autouse=True)
    def _no_background_tasks(self):
        """Patch background tasks to avoid infinite loops.

        maintenance_task() runs an infinite while True loop.  The patched
        version completes immediately so the event loop can exit cleanly.
        """
        async def _noop_maintenance():
            pass  # one-shot, no loop

        with patch("discord_bot.asyncio.sleep", AsyncMock()):
            with patch("discord_bot.maintenance_task", side_effect=_noop_maintenance):
                yield

    @pytest.mark.asyncio
    async def test_main_retries_on_aiohttp_error(self):
        """main() retries connection after aiohttp.ClientError, then succeeds.

        On success, the bot calls client.start() which eventually blocks forever.
        We simulate "success" by raising SystemExit (which propagates out
        through main() -> asyncio.run -> test runner).
        """
        import discord_bot

        start_count = 0

        async def mock_start(token):
            nonlocal start_count
            start_count += 1
            if start_count < 3:
                raise __import__("aiohttp").ClientError("Connection failed")
            # Simulates normal operation (client.start() blocks forever)
            raise SystemExit(0)

        discord_bot.client.start = AsyncMock(side_effect=mock_start)
        discord_bot.client.is_closed = MagicMock(return_value=True)

        with pytest.raises(SystemExit):
            await discord_bot.main()

        # Should have called start 3 times (2 failures + 1 success)
        assert discord_bot.client.start.await_count == 3

    @pytest.mark.asyncio
    async def test_main_retries_exhausted(self):
        """main() tries MAX_RETRIES times then gives up (error swallowed)."""
        import discord_bot

        async def mock_start(token):
            raise __import__("aiohttp").ClientError("Persistent failure")

        discord_bot.client.start = AsyncMock(side_effect=mock_start)
        discord_bot.client.is_closed = MagicMock(return_value=True)

        # After last retry, the inner raise propagates to the outer except
        # Exception handler which logs and returns normally
        await discord_bot.main()

        # Should have tried exactly 5 times (MAX_RETRIES)
        assert discord_bot.client.start.await_count == 5
