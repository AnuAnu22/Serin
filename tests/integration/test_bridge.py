"""Integration tests for voice bridge — protocol parsing and bridge lifecycle."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from serin.d1_2_gateway_io.d2_4_io_di import init_gateway
from serin.d1_4_config_base.d2_3_core_logger import logger as _default_logger

# RustVoiceBridge.__init__ calls get_logger() (gateway DI). Initialize the same
# way tests/messaging/test_processor.py does, so constructing the bridge in a
# bare test process doesn't raise "Gateway not initialized".
init_gateway(_default_logger)

from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.d4_1_io_bridge import (  # noqa: E402
    RustStdoutReader,
)
from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.d4_4_process_watch.d5_1_process_watch import (  # noqa: E402
    RustVoiceBridge,
)


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
