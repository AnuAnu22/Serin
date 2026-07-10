from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_discord_client() -> MagicMock:
    client = MagicMock()
    client.is_ready.return_value = True
    client.latency = 0.05
    client.user.id = 12345
    client.user.name = "SerinBot"
    client.user.discriminator = "0000"
    client.guilds = []
    return client


@pytest.fixture
def mock_memory_system() -> MagicMock:
    mem = MagicMock()
    mem.qdrant_client = MagicMock()
    return mem


@pytest.fixture
def mock_background_processor() -> MagicMock:
    bg = MagicMock()
    bg.is_running = True
    bg.processing_queue = []
    bg.get_stats = MagicMock(return_value={"queue_size": 0, "processed": 10})
    bg.start = AsyncMock()
    bg.stop = AsyncMock()
    return bg


@pytest.fixture
def bot_state_dict(
    mock_discord_client: MagicMock,
    mock_memory_system: MagicMock,
    mock_background_processor: MagicMock,
) -> dict:
    from serin.d1_5_ops_tooling.control_panel.server.state import bot_state
    bot_state.clear()
    bot_state["discord_client"] = mock_discord_client
    bot_state["memory_system"] = mock_memory_system
    bot_state["background_processor"] = mock_background_processor
    bot_state["message_manager"] = MagicMock()
    bot_state["passive_monitor"] = MagicMock()
    bot_state["message_crawler"] = MagicMock()
    bot_state["voice_listener"] = None
    bot_state["tts_engine"] = None
    bot_state["bot_stats"] = {"messages_processed": 100}
    return bot_state


@pytest.fixture
def client(bot_state_dict: dict) -> TestClient:
    from serin.d1_5_ops_tooling.control_panel.server import app
    return TestClient(app)
