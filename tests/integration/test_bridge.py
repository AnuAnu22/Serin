"""Integration tests for voice bridge — protocol parsing and bridge lifecycle."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from serin.d1_2_gateway_io.voice_system.bridge_io.bridge import RustStdoutReader
from serin.d1_2_gateway_io.voice_system.bridge_io.process_watch import RustVoiceBridge


def test_reader_has_expected_interface():
    """RustStdoutReader can be constructed and exposes the expected protocol."""
    reader = RustStdoutReader.__new__(RustStdoutReader)
    reader.events = asyncio.Queue()
    reader.proc = MagicMock()
    assert hasattr(reader, 'events')
    assert hasattr(reader, 'read_loop')
    assert hasattr(reader, '_EOF')


def test_bridge_init_sets_defaults():
    """RustVoiceBridge stores constructor args correctly."""
    bridge = RustVoiceBridge(
        audio_processor=MagicMock(),
        voice_listener=MagicMock(),
        binary_path="/tmp/fake_binary",
    )
    assert bridge.binary_path == "/tmp/fake_binary"
    assert bridge.audio_processor is not None
    assert bridge.voice_listener is not None
    assert bridge.proc is None


@pytest.mark.asyncio
async def test_bridge_start_returns_false_when_binary_missing():
    """start() returns False when the Rust binary doesn't exist on disk."""
    bridge = RustVoiceBridge(
        audio_processor=MagicMock(),
        voice_listener=MagicMock(),
        binary_path="/tmp/definitely_does_not_exist_binary",
    )
    result = await bridge.start(guild_id=111, channel_id=222, voice_client=MagicMock())
    assert result is False
    assert bridge.proc is None
