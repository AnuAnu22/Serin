"""
Integration tests for voice/bridge.py — Rust subprocess lifecycle and protocol parsing.

Tests the Python-side protocol parser (RustStdoutReader) and bridge lifecycle
(start/stop/send_tts_audio/interrupt) using mocked subprocess pipes.

These tests do NOT require the actual Rust binary — all subprocess I/O
is simulated via MagicMock pipes.
"""
from __future__ import annotations

import io
import json
import queue
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.bridge import RustStdoutReader
from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.process_watch import RustVoiceBridge

# =========================================================================
# RustStdoutReader protocol parsing tests
# =========================================================================


def _make_reader(pipe_data: bytes) -> tuple:
    """Create a RustStdoutReader with a mock subprocess and pre-loaded pipe data.

    Returns (reader, mock_proc) so the caller can inspect or manipulate the process.
    """
    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.stdout = io.BytesIO(pipe_data)
    mock_proc.stderr = io.BytesIO(b"")

    with patch("voice.bridge.threading.Thread"):
        reader = RustStdoutReader(mock_proc)
    return reader, mock_proc


class TestRustStdoutReader:
    """Tests for the stdout protocol parser that runs in a background thread."""

    def test_audio_event_parsed_correctly(self):
        """AUDIO:{user_id}:{pcm_len}\\n followed by pcm bytes produces ('audio', user_id, pcm)."""
        pcm_payload = b"\x00\x01\x02\x03" * 256  # 1024 bytes
        data = f"AUDIO:user123:{len(pcm_payload)}\n".encode() + pcm_payload
        reader, _ = _make_reader(data)
        reader._run()  # synchronous call for testing

        events = _drain_tuples(reader.events)
        audio_events = [e for e in events if e[0] == "audio"]
        assert len(audio_events) == 1
        assert audio_events[0][1] == "user123"
        assert audio_events[0][2] == pcm_payload

    def test_join_event_parsed(self):
        """JOIN:{user_id} produces ('join', user_id)."""
        data = b"JOIN:user456\n"
        reader, _ = _make_reader(data)
        reader._run()
        events = _drain_queue(reader.events)
        assert ("join", "user456") in events

    def test_leave_event_parsed(self):
        """LEAVE:{user_id} produces ('leave', user_id)."""
        data = b"LEAVE:user789\n"
        reader, _ = _make_reader(data)
        reader._run()
        events = _drain_queue(reader.events)
        assert ("leave", "user789") in events

    def test_tts_done_event_parsed(self):
        """TTS_DONE produces ('tts_done',)."""
        data = b"TTS_DONE\n"
        reader, _ = _make_reader(data)
        reader._run()
        events = _drain_queue(reader.events)
        assert ("tts_done",) in events

    def test_log_lines_forwarded(self):
        """Unknown lines produce ('log', line)."""
        data = b"some log message from rust\n"
        reader, _ = _make_reader(data)
        reader._run()
        events = _drain_queue(reader.events)
        assert ("log", "some log message from rust") in events

    def test_eof_sentinel(self):
        """Empty pipe (process died) puts _EOF sentinel in queue."""
        reader, _ = _make_reader(b"")
        reader._run()
        assert reader.events.get_nowait() is reader._EOF

    def test_multiple_events_in_one_chunk(self):
        """Multiple newline-delimited lines in a single chunk are all parsed."""
        data = b"JOIN:u1\nLEAVE:u1\nTTS_DONE\nLOG:hello\n"
        reader, _ = _make_reader(data)
        reader._run()
        events = _drain_queue(reader.events)
        assert ("join", "u1") in events
        assert ("leave", "u1") in events
        assert ("tts_done",) in events
        assert ("log", "LOG:hello") in events

    def test_get_returns_none_on_timeout(self):
        """get() returns None when queue is empty (timeout)."""
        reader, _ = _make_reader(b"")
        reader.events = queue.Queue()  # fresh empty queue
        result = reader.get(timeout=0.01)
        assert result is None

    def test_get_raises_eoferror_on_eof(self):
        """get() raises EOFError when _EOF sentinel is at front of queue."""
        reader, _ = _make_reader(b"")
        reader.events = queue.Queue()
        reader.events.put(reader._EOF)
        with pytest.raises(EOFError):
            reader.get(timeout=0.01)

    def test_audio_with_exact_pcm_boundary(self):
        """AUDIO event with exactly the right amount of PCM data is parsed."""
        pcm = b"\xff" * 64
        data = b"AUDIO:u:64\n" + pcm
        reader, _ = _make_reader(data)
        reader._run()
        events = _drain_tuples(reader.events)
        audio_events = [e for e in events if e[0] == "audio"]
        assert len(audio_events) == 1
        assert audio_events[0][2] == pcm


# =========================================================================
# RustVoiceBridge lifecycle tests
# =========================================================================


@pytest.fixture
def mock_audio_processor():
    """Mock AudioStreamProcessor."""
    ap = MagicMock()
    ap.process_audio_chunk = AsyncMock()
    ap._release_lock = MagicMock()
    return ap


@pytest.fixture
def mock_voice_listener():
    """Mock VoiceListener with voice_connections dict."""
    vl = MagicMock()
    vl.voice_connections = {}
    return vl


@pytest.fixture
def mock_process():
    """Mock subprocess.Popen instance."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.poll.return_value = None  # alive
    proc.stdout = io.BytesIO(b"")
    proc.stderr = io.BytesIO(b"")
    proc.stdin = io.BytesIO()
    return proc


# Patch locations
POPEN = "voice.bridge.subprocess.Popen"
EXISTS = "voice.bridge.os.path.exists"


def _make_bridge(*, mock_audio_processor, mock_voice_listener):
    """Create a RustVoiceBridge with patched threading.Thread (no-op)."""
    with patch("voice.bridge.threading.Thread"):
        return RustVoiceBridge(mock_audio_processor, mock_voice_listener)


# Decorator to prevent background async tasks from actually running.
# These methods are replaced with AsyncMock so asyncio.create_task() can
# schedule them without hanging (AsyncMock returns a completed coroutine).
_NOOP_BG_TASKS = [
    patch.object(RustVoiceBridge, "_read_loop", new_callable=AsyncMock),
    patch.object(RustVoiceBridge, "_supervise_rust_process", new_callable=AsyncMock),
]


class TestRustVoiceBridgeLifecycle:
    """Tests for RustVoiceBridge start/stop lifecycle and stdin protocol."""

    @pytest.mark.asyncio
    @patch(POPEN)
    @patch(EXISTS, return_value=True)
    async def test_start_with_info_returns_true(
        self, mock_exists, mock_popen,
        mock_audio_processor, mock_voice_listener, mock_process
    ):
        """start_with_info() returns True when subprocess launches successfully."""
        mock_popen.return_value = mock_process
        with _patch_bg_tasks():
            bridge = _make_bridge(
                mock_audio_processor=mock_audio_processor,
                mock_voice_listener=mock_voice_listener,
            )
            info = {"endpoint": "test.example.com", "token": "tok", "session_id": "sid"}
            result = await bridge.start_with_info(11111, 22222, info)

        assert result is True
        assert bridge.is_running()

    @pytest.mark.asyncio
    @patch(POPEN)
    @patch(EXISTS, return_value=True)
    async def test_start_sends_connection_info_as_json(
        self, mock_exists, mock_popen,
        mock_audio_processor, mock_voice_listener, mock_process
    ):
        """First stdin write should be JSON ConnectionInfo."""
        mock_popen.return_value = mock_process
        with _patch_bg_tasks():
            bridge = _make_bridge(
                mock_audio_processor=mock_audio_processor,
                mock_voice_listener=mock_voice_listener,
            )
            info = {"endpoint": "test.example.com", "token": "tok", "session_id": "sid"}
            await bridge.start_with_info(11111, 22222, info)

        # Inspect what was written to stdin
        written = mock_process.stdin.getvalue()
        first_line = written.split(b"\n")[0]
        sent = json.loads(first_line.decode())
        assert sent == info

    @pytest.mark.asyncio
    @patch(POPEN)
    @patch(EXISTS, return_value=True)
    async def test_start_with_info_sets_state(
        self, mock_exists, mock_popen,
        mock_audio_processor, mock_voice_listener, mock_process
    ):
        """After start_with_info, bridge state should reflect the guild/channel."""
        mock_popen.return_value = mock_process
        with _patch_bg_tasks():
            bridge = _make_bridge(
                mock_audio_processor=mock_audio_processor,
                mock_voice_listener=mock_voice_listener,
            )
            info = {"endpoint": "ep", "token": "tok", "session_id": "sid"}
            await bridge.start_with_info(99999, 33333, info)

        assert bridge._guild_id == 99999
        assert bridge._channel_id == 33333
        assert bridge._running is True
        assert bridge._shutdown_requested is False

    @pytest.mark.asyncio
    @patch(POPEN)
    @patch(EXISTS, return_value=True)
    async def test_start_returns_false_when_binary_missing(
        self, mock_exists, mock_popen,
        mock_audio_processor, mock_voice_listener
    ):
        """start_with_info() returns False when binary does not exist."""
        mock_exists.return_value = False  # binary not found
        bridge = _make_bridge(
            mock_audio_processor=mock_audio_processor,
            mock_voice_listener=mock_voice_listener,
        )
        info = {"endpoint": "ep", "token": "tok", "session_id": "sid"}
        result = await bridge.start_with_info(11111, 22222, info)

        assert result is False
        mock_popen.assert_not_called()

    @pytest.mark.asyncio
    @patch(POPEN)
    @patch(EXISTS, return_value=True)
    async def test_stop_sends_shutdown(
        self, mock_exists, mock_popen,
        mock_audio_processor, mock_voice_listener, mock_process
    ):
        """stop() writes SHUTDOWN to stdin, kills process, cleans up."""
        mock_popen.return_value = mock_process
        with _patch_bg_tasks():
            bridge = _make_bridge(
                mock_audio_processor=mock_audio_processor,
                mock_voice_listener=mock_voice_listener,
            )
            info = {"endpoint": "ep", "token": "tok", "session_id": "sid"}
            await bridge.start_with_info(11111, 22222, info)

        # Keep the mock_proc reference for inspection after start_with_info
        mock_stdin = mock_process.stdin

        await bridge.stop()

        # Should have written SHUTDOWN
        written = mock_stdin.getvalue()
        assert b"SHUTDOWN" in written

        # State should be cleaned up
        assert bridge.is_running() is False
        assert bridge.proc is None

    @pytest.mark.asyncio
    @patch(POPEN)
    @patch(EXISTS, return_value=True)
    async def test_send_tts_audio_writes_speak_command(
        self, mock_exists, mock_popen,
        mock_audio_processor, mock_voice_listener, mock_process
    ):
        """send_tts_audio() should write SPEAK:{len} + PCM data to stdin."""
        mock_popen.return_value = mock_process
        with _patch_bg_tasks():
            bridge = _make_bridge(
                mock_audio_processor=mock_audio_processor,
                mock_voice_listener=mock_voice_listener,
            )
            info = {"endpoint": "ep", "token": "tok", "session_id": "sid"}
            await bridge.start_with_info(11111, 22222, info)

        pcm_data = b"\x00\x01" * 100
        await bridge.send_tts_audio(pcm_data)

        written = mock_process.stdin.getvalue()
        assert b"SPEAK:" in written
        # Parse the payload length from the SPEAK header
        parts = written.split(b"\n")
        speak_line = next(line for line in parts if line.startswith(b"SPEAK:"))
        length = int(speak_line[len(b"SPEAK:"):])
        assert length == len(pcm_data)

    @pytest.mark.asyncio
    @patch(POPEN)
    @patch(EXISTS, return_value=True)
    async def test_interrupt_sends_interrupt_command(
        self, mock_exists, mock_popen,
        mock_audio_processor, mock_voice_listener, mock_process
    ):
        """interrupt() should write INTERRUPT to stdin."""
        mock_popen.return_value = mock_process
        with _patch_bg_tasks():
            bridge = _make_bridge(
                mock_audio_processor=mock_audio_processor,
                mock_voice_listener=mock_voice_listener,
            )
            info = {"endpoint": "ep", "token": "tok", "session_id": "sid"}
            await bridge.start_with_info(11111, 22222, info)

        await bridge.interrupt()

        written = mock_process.stdin.getvalue()
        assert b"INTERRUPT\n" in written

    @pytest.mark.asyncio
    async def test_interrupt_noop_when_process_dead(
        self, mock_audio_processor, mock_voice_listener
    ):
        """interrupt() should no-op when process is None (not started)."""
        bridge = _make_bridge(
            mock_audio_processor=mock_audio_processor,
            mock_voice_listener=mock_voice_listener,
        )
        assert bridge.proc is None
        await bridge.interrupt()

    def test_handle_tts_done_releases_lock(
        self, mock_audio_processor, mock_voice_listener
    ):
        """_handle_tts_done should call audio_processor._release_lock."""
        bridge = _make_bridge(
            mock_audio_processor=mock_audio_processor,
            mock_voice_listener=mock_voice_listener,
        )
        bridge._guild_id = 11111
        bridge._handle_tts_done()
        mock_audio_processor._release_lock.assert_called_once_with("11111")

    def test_get_stats_returns_dict(
        self, mock_audio_processor, mock_voice_listener
    ):
        """get_stats() returns a dict with process state."""
        bridge = _make_bridge(
            mock_audio_processor=mock_audio_processor,
            mock_voice_listener=mock_voice_listener,
        )
        stats = bridge.get_stats()
        assert isinstance(stats, dict)
        assert "process_alive" in stats
        assert "guild_id" in stats
        assert "channel_id" in stats

    def test_is_running_initially_false(
        self, mock_audio_processor, mock_voice_listener
    ):
        """is_running() returns False before start()."""
        bridge = _make_bridge(
            mock_audio_processor=mock_audio_processor,
            mock_voice_listener=mock_voice_listener,
        )
        assert bridge.is_running() is False

    @pytest.mark.asyncio
    @patch(POPEN)
    @patch(EXISTS, return_value=True)
    async def test_full_start_stop_cycle(
        self, mock_exists, mock_popen,
        mock_audio_processor, mock_voice_listener, mock_process
    ):
        """Full start -> send_tts -> interrupt -> stop cycle works."""
        mock_popen.return_value = mock_process
        with _patch_bg_tasks():
            bridge = _make_bridge(
                mock_audio_processor=mock_audio_processor,
                mock_voice_listener=mock_voice_listener,
            )
            info = {"endpoint": "ep", "token": "tok", "session_id": "sid"}

            # Start
            assert await bridge.start_with_info(11111, 22222, info) is True
            assert bridge.is_running()

        # Send TTS
        await bridge.send_tts_audio(b"\x00" * 320)
        assert b"SPEAK:" in mock_process.stdin.getvalue()

        # Interrupt
        await bridge.interrupt()
        assert b"INTERRUPT\n" in mock_process.stdin.getvalue()

        # Stop
        await bridge.stop()
        assert bridge.proc is None


# =========================================================================
# Helpers
# =========================================================================


def _drain_queue(q: queue.Queue) -> list:
    """Drain a queue into a list (includes sentinel objects)."""
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            break
    return items


def _drain_tuples(q: queue.Queue) -> list[tuple]:
    """Drain a queue, returning only tuple items (filters out _EOF sentinel)."""
    return [item for item in _drain_queue(q) if isinstance(item, tuple)]


def _patch_bg_tasks():
    """Context manager that replaces background async tasks with no-ops.

    This prevents unawaited-coroutine warnings by ensuring the coroutines
    created in start_with_info() are properly handled by AsyncMock.
    """
    from unittest.mock import AsyncMock

    from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.process_watch import RustVoiceBridge
    return patch.multiple(
        RustVoiceBridge,
        _read_loop=AsyncMock(),
        _supervise_rust_process=AsyncMock(),
    )
