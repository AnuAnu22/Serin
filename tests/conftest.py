"""
Shared pytest fixtures for Serin tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from serin.d1_3_state_core.message_context import MessageContext


@pytest.fixture
def mock_message():
    """A minimal discord.Message mock (AsyncMock for await-able methods)."""
    msg = MagicMock()
    msg.author.id = 12345
    msg.author.display_name = "TestUser"
    msg.channel.id = 67890
    msg.guild.id = 11111
    msg.content = "hey serin what's up"
    msg.guild = MagicMock()
    msg.guild.id = 11111
    msg.guild.me = MagicMock()
    # SendStage does await channel.send(...)
    msg.channel.send = AsyncMock()
    msg.reply = AsyncMock()
    return msg


@pytest.fixture
def base_context(mock_message):
    """A MessageContext with sensible defaults for testing."""
    return MessageContext(
        message=mock_message,
        user_id="12345",
        username="TestUser",
        channel_id="67890",
        guild_id="11111",
        raw_content="hey serin what's up",
    )
