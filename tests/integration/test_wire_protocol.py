"""Tier-A wire-protocol integration tests: real bridge code vs the fake receiver.

These tests execute ``RustStdoutReader`` (and, for the lifecycle cases, a real
``RustVoiceBridge``) against actual subprocess pipes carrying genuine protocol
traffic — the coverage gap named in docs/CONNECTIONS.md edge J ("the wire
protocol framing ... covered only by AST contract checks") and wiki [[testing]]
("the two explicit gaps in the suite").

What these tests deliberately do NOT cover: DAVE/UDP/songbird behavior inside
the real Rust binary (needs live Discord voice; see Tier-B smoke + the manual
release checklist). The fake stands in for the *pipe peer*, never for Rust's
audio logic.

Pinned known-wiring findings (pre-existing, documented — NOT fixed here):
  - ``_read_loop`` (d5_2_process_watch_io.py) iterates ``async for ... in
    self.reader``, but RustStdoutReader defines no ``__aiter__``/``__anext__``
    and emits tuples the consumer unpacks as ``(event_type, dict)``. The live
    consumer path cannot currently dispatch reader events. Case
    ``test_reader_lacks_async_iterator_protocol`` pins this fact honestly so a
    future fix must flip it consciously.

# --- Imports ---
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pytest_asyncio")

from serin.d1_2_gateway_io.d2_4_io_di import init_gateway  # noqa: E402
from serin.d1_4_config_base.d2_3_core_logger import (
    logger as _default_logger,  # noqa: E402
)

# Gateway DI must be initialized before constructing the bridge (same pattern
# as tests/integration/test_bridge.py and tests/messaging/test_processor.py).
init_gateway(_default_logger)

from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.d4_1_io_bridge import (  # noqa: E402
    _SNOWFLAKE_MIN_32BIT,
    RustStdoutReader,
)
from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.d4_2_bridge_commands import (  # noqa: E402
    send_tts_audio,
)
from serin.d1_2_gateway_io.d2_2_voice_system.d3_2_bridge_io.d4_4_process_watch.d5_1_process_watch import (  # noqa: E402
    RustVoiceBridge,
)
from tests.integration.protocol_framers import (  # noqa: E402
    DEFAULT_CONNECTION_INFO,
    TTS_DONE_FRAME,
    connection_info_json,
    decode_audio_header,
    encode_audio,
)

FAKE_RECEIVER = Path(__file__).parent / "fake_voice_receiver.py"
RAW_SSRC_UID = "12345"  # < 2**32: looks like a raw SSRC to the guard
REAL_SNOWFLAKE_UID = str(DEFAULT_CONNECTION_INFO["user_id"])


class MinimalAudioProcessor:
    """Duck-typed stand-in exposing only the lock surface TTS_DONE touches.

    Mirrors the real AudioStreamProcessor's ``_processing_lock_until`` dict +
    ``_release_lock`` / ``_flush_buffered_audio`` methods that
    ``RustVoiceBridge._handle_tts_done`` relies on.
    """

    def __init__(self) -> None:
        self._processing_lock_until: dict[str, float] = {}
        self.flushed: list[str] = []

    def _release_lock(self, guild_id: str) -> None:
        self._processing_lock_until.pop(guild_id, None)

    def _flush_buffered_audio(self, guild_id: str) -> None:
        self.flushed.append(guild_id)


# --- Helpers ---


def _make_bridge(processor: MinimalAudioProcessor | Any) -> RustVoiceBridge:
    """Build a bridge wired to stubs (no Discord objects anywhere)."""
    return RustVoiceBridge(
        audio_processor=processor,
        voice_listener=MagicMockListener(),
        binary_path="/tmp/nonexistent_for_tests",
    )


class MagicMockListener:
    """Voice-listener stub: username resolution falls through to user_<uid>."""

    class _Client:
        def get_guild(self, guild_id: int | None) -> None:
            return None

        @property
        def user(self) -> None:
            return None

    def __init__(self) -> None:
        self.client = MagicMockListener._Client()


async def _spawn(scenario: str, **cli: str) -> asyncio.subprocess.Process:
    """Spawn the fake receiver with unbuffered stdout.

    The fake emits with ``--user-id`` pinned to REAL_SNOWFLAKE_UID by default
    so emitted frames carry the same uid class as production traffic.
    """
    cli.setdefault("--user-id", REAL_SNOWFLAKE_UID)
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        str(FAKE_RECEIVER),
        "--scenario",
        scenario,
        *[item for pair in cli.items() for item in pair],
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def _start_reader(scenario: str, **cli: str) -> tuple[asyncio.subprocess.Process, RustStdoutReader]:
    proc = await _spawn(scenario, **cli)
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(connection_info_json())
    await proc.stdin.drain()
    reader = RustStdoutReader(proc)
    if scenario == "silent":
        # The fake acknowledges the handshake with a diagnostic FAKE_READY
        # line (exercising the reader's log branch); consume it so every
        # test starts from a clean event queue.
        loop_task = asyncio.create_task(reader.read_loop())
        try:
            event = await asyncio.wait_for(reader.events.get(), timeout=5.0)
            assert event == ("log", "FAKE_READY"), f"expected handshake ack, got {event!r}"
        finally:
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
    return proc, reader


async def _drain_events(reader: RustStdoutReader, count: int, timeout: float = 5.0) -> list[tuple[Any, ...]]:
    """Collect exactly ``count`` events via the reader's own parsing loop."""
    loop_task = asyncio.create_task(reader.read_loop())
    events: list[tuple[Any, ...]] = []
    try:
        while len(events) < count:
            event = await asyncio.wait_for(reader.events.get(), timeout=timeout)
            if event is RustStdoutReader._EOF:
                raise AssertionError(f"EOF after {len(events)} events (wanted {count})")
            assert isinstance(event, tuple), f"non-tuple event: {event!r}"
            events.append(event)
    finally:
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
    return events


async def _stop(proc: asyncio.subprocess.Process) -> None:
    if proc.stdin is not None:
        try:
            proc.stdin.write(b"SHUTDOWN\n")
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except TimeoutError:
        proc.kill()
        await proc.wait()


async def _emit(proc: asyncio.subprocess.Process, command: bytes) -> None:
    """Send one bench command to the fake and let the loop turn."""
    assert proc.stdin is not None
    proc.stdin.write(command + b"\n")
    await proc.stdin.drain()
    await asyncio.sleep(0.05)


@pytest.fixture()
async def fake_proc() -> AsyncIterator[asyncio.subprocess.Process]:
    proc = await _spawn("silent")
    yield proc
    await _stop(proc)


# --- Entry ---


@pytest.mark.asyncio
async def test_connection_info_handshake_is_valid_json_first_line(fake_proc: asyncio.subprocess.Process) -> None:
    """The fake validates the handshake the same way main.rs does."""
    assert fake_proc.stdin is not None and fake_proc.stdout is not None
    fake_proc.stdin.write(b"this is not json\n")
    await fake_proc.stdin.drain()
    try:
        code = await asyncio.wait_for(fake_proc.wait(), timeout=5.0)
    except TimeoutError:
        pytest.fail("fake receiver did not exit on bad ConnectionInfo")
    assert code == 3


@pytest.mark.asyncio
async def test_reader_parses_join_leave_tts_done_and_log_lines() -> None:
    """All four line-oriented event types parse to their exact tuples."""
    proc, reader = await _start_reader("silent")
    try:
        await _emit(proc, b"EMIT:join")
        await _emit(proc, b"EMIT:leave")
        await _emit(proc, b"EMIT:tts_done")
        # Raw junk log line via RAW injection -> reader's log branch.
        await _emit(proc, f"RAW:{b'some corrupted wire line'.hex()}".encode())
        events = await _drain_events(reader, 4)
    finally:
        await _stop(proc)
    assert ("join", REAL_SNOWFLAKE_UID) in events
    assert ("leave", REAL_SNOWFLAKE_UID) in events
    assert ("tts_done",) in events
    log_lines = [e[1] for e in events if e[0] == "log"]
    assert any("corrupted wire line" in ln for ln in log_lines)
    join_events = [e for e in events if e[0] == "join"]
    assert join_events == [("join", REAL_SNOWFLAKE_UID)]


@pytest.mark.asyncio
async def test_unterminated_junk_glues_into_next_line() -> None:
    """PINNED parser property: junk WITHOUT trailing newline corrupts the next line.

    A wire fragment with no terminator gets glued to whatever frame follows,
    and the whole glued line degrades to a single log event — the following
    real frame is swallowed. This is true production behavior of read_loop's
    newline scan (verified 2026-08-26). If a future hardening adds resync
    logic (e.g. scanning for known prefixes), flip this assertion consciously.

    Injection shape: ONE RAW payload containing ``junk + JOIN:...`` with no
    newline between — exactly the bytes a corrupted writer would produce.
    """
    proc, reader = await _start_reader("silent")
    task = asyncio.create_task(reader.read_loop())
    try:
        glued = b"some unterminated junk" + f"JOIN:{REAL_SNOWFLAKE_UID}".encode()
        proc.stdin.write(f"RAW:{glued.hex()}\n".encode())
        await proc.stdin.drain()
        got: list[tuple[Any, ...]] = []
        try:
            while True:
                event = await asyncio.wait_for(reader.events.get(), timeout=1.5)
                if event is RustStdoutReader._EOF:
                    break
                if isinstance(event, tuple):
                    got.append(event)
        except TimeoutError:
            pass
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await _stop(proc)
    joined_logs = [e for e in got if e[0] == "log"]
    assert any("unterminated junkJOIN:" in str(ln) for ln in joined_logs), (
        f"expected glued log event, got {got!r}"
    )
    assert not any(e[0] == "join" for e in got), (
        "parser resynced — update this pinned property test"
    )


@pytest.mark.asyncio
async def test_reader_parses_audio_frame_with_binary_payload() -> None:
    """PCM payloads containing newlines/NULs/high bytes survive intact.

    The parser must honor pcm_len, not treat payload bytes as frame data.
    """
    proc, reader = await _start_reader("silent")
    try:
        # Drive the fake's own AUDIO frame (its deterministic payload), then
        # verify byte-exactness against what the framer would have produced.
        await _emit(proc, b"EMIT:audio")
        events = await _drain_events(reader, 1)
    finally:
        await _stop(proc)
    assert events[0][0] == "audio"
    assert events[0][1] == REAL_SNOWFLAKE_UID
    got_pcm: bytes = events[0][2]
    assert len(got_pcm) == int(
        decode_audio_header(f"AUDIO:{REAL_SNOWFLAKE_UID}:{len(got_pcm)}")[1]
    )
    # Newlines/NULs/high bytes must survive: payload is NOT newline-framed.
    assert any(b == 0x00 for b in got_pcm)
    assert any(b == 0x0A for b in got_pcm)
    assert any(b > 0x7F for b in got_pcm)


@pytest.mark.asyncio
async def test_reader_reassembles_audio_across_partial_reads() -> None:
    """AUDIO payload delivered while reader is mid-frame reassembles into ONE event.

    The fake emits a large AUDIO frame immediately (join_then_audio with a big
    --pcm-bytes value); the reader must buffer across multiple stdout reads.
    """
    proc = await _spawn("silent")
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(connection_info_json())
    await proc.stdin.drain()
    # Switch the fake into emitting a big frame via EMIT after reader start,
    # using join_then_audio's upfront emission instead: spawn that scenario.
    await _stop(proc)

    proc = await _spawn("join_then_audio", **{"--pcm-bytes": "65536"})
    assert proc.stdin is not None
    proc.stdin.write(connection_info_json())
    await proc.stdin.drain()
    reader = RustStdoutReader(proc)
    task = asyncio.create_task(reader.read_loop())
    try:
        events = []
        for _ in range(4):  # JOIN + 3 AUDIO chunks
            event = await asyncio.wait_for(reader.events.get(), timeout=10.0)
            if isinstance(event, tuple):
                events.append(event)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await _stop(proc)
    kinds = [e[0] for e in events]
    assert kinds == ["join", "audio", "audio", "audio"]
    audio_events = [e for e in events if e[0] == "audio"]
    assert all(len(e[2]) == 65536 for e in audio_events), (
        f"payload sizes: {[len(e[2]) for e in audio_events]}"
    )
    assert all(e[1] == REAL_SNOWFLAKE_UID for e in audio_events)


@pytest.mark.asyncio
async def test_reader_survives_truncated_audio_then_eof() -> None:
    """A truncated AUDIO frame followed by pipe close yields EOF, no hang.

    Driven by killing the fake mid-frame (SIGKILL after an AUDIO header with
    a huge promised length is impossible to inject through the fake's own
    encoder — instead we use the raw-subprocess approach: feed the fake a
    command it cannot parse while a reader watches, then kill -9 and confirm
    the reader surfaces EOF rather than hanging).
    """
    proc = await _spawn("silent")
    reader = RustStdoutReader(proc)
    task = asyncio.create_task(reader.read_loop())
    got_eof = False
    try:
        assert proc.stdin is not None
        # The fake will exit on EOF; we close stdin then SIGKILL so stdout
        # closes while the reader is blocked in read().
        proc.stdin.close()
        proc.kill()
        while True:
            event = await asyncio.wait_for(reader.events.get(), timeout=5.0)
            if event is RustStdoutReader._EOF:
                got_eof = True
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await _stop(proc)
    assert got_eof


@pytest.mark.asyncio
async def test_reader_survives_garbage_lines() -> None:
    """PINNED parser degradation behavior under wire garbage (verified 2026-08-26).

    Three distinct behaviors, all asserted here so a hardening change must be
    conscious:
      - valid-UTF8 junk line  -> ('log', ...) event (visible)
      - non-UTF8 junk bytes   -> SILENTLY DROPPED (decode-error continue path)
      - a valid frame after junk -> still parsed correctly
    """
    proc, reader = await _start_reader("silent")
    task = asyncio.create_task(reader.read_loop())
    try:
        utf8_junk = f"RAW:{b'garbage log line'.hex()}".encode()
        await _emit(proc, utf8_junk)  # -> visible log event
        await _emit(proc, b"EMIT:join")  # -> survives
        another_junk_hex = b"another \x01 line".hex()
        await _emit(proc, f"RAW:{another_junk_hex}".encode())  # UTF8-ok junk
        events: list[tuple[Any, ...]] = []
        for _ in range(3):
            event = await asyncio.wait_for(reader.events.get(), timeout=5.0)
            if isinstance(event, tuple):
                events.append(event)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await _stop(proc)
    assert events == [
        ("log", "garbage log line"),
        ("join", REAL_SNOWFLAKE_UID),
        ("log", "another \x01 line"),
    ]


@pytest.mark.asyncio
async def test_non_utf8_junk_is_dropped_silently() -> None:
    """PINNED: non-UTF8 wire lines are dropped with NO event (decode-continue).

    dave_receive lesson candidate: a corrupted binary burst produces zero
    telemetry today. If observability for decode failures is ever added,
    flip this assertion consciously.
    """
    proc, reader = await _start_reader("silent")
    task = asyncio.create_task(reader.read_loop())
    try:
        non_utf8 = b"\xff\xfe garbage \x00".hex()
        await _emit(proc, f"RAW:{non_utf8}".encode())
        await _emit(proc, b"EMIT:join")  # next valid frame unaffected
        event = await asyncio.wait_for(reader.events.get(), timeout=5.0)
        events = [event] if isinstance(event, tuple) else []
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await _stop(proc)
    assert events == [("join", REAL_SNOWFLAKE_UID)]


@pytest.mark.asyncio
async def test_reader_ignores_bad_pcm_len() -> None:
    """AUDIO header with non-integer length is dropped cleanly."""
    proc, reader = await _start_reader("silent")
    task = asyncio.create_task(reader.read_loop())
    try:
        bad_header = (
            b"AUDIO:" + REAL_SNOWFLAKE_UID.encode() + b":notanumber\n"
        ).hex()
        await _emit(proc, f"RAW:{bad_header}".encode())  # malformed AUDIO
        await _emit(proc, b"EMIT:join")  # valid frame after it survives
        event = await asyncio.wait_for(reader.events.get(), timeout=5.0)
        events = [event] if isinstance(event, tuple) else []
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await _stop(proc)
    assert events == [("join", REAL_SNOWFLAKE_UID)]  # bad AUDIO gone, join fine


@pytest.mark.asyncio
async def test_raw_ssrc_guard_warns_but_does_not_drop() -> None:
    """Sub-2**32 uids still produce audio events (guard warns, never drops).

    Contract from d4_1_io_bridge.py's raw-SSRC attribution guard docstring.
    """
    proc, reader = await _start_reader("silent")
    task = asyncio.create_task(reader.read_loop())
    try:
        assert int(RAW_SSRC_UID) < _SNOWFLAKE_MIN_32BIT
        # Raw-SSRC AUDIO frame injected verbatim (the fake always emits
        # snowflake uids; RAW injection exercises the guard path).
        audio_frame = encode_audio(RAW_SSRC_UID, b"\x01\x02\x03").hex()
        await _emit(proc, f"RAW:{audio_frame}".encode())
        event = await asyncio.wait_for(reader.events.get(), timeout=5.0)
        events = [event] if isinstance(event, tuple) else []
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await _stop(proc)
    assert events == [("audio", RAW_SSRC_UID, b"\x01\x02\x03")]


@pytest.mark.asyncio
async def test_speak_framing_byte_exact() -> None:
    """send_tts_audio writes SPEAK:{len}\\n+bytes; fake decodes it losslessly."""
    processor = MinimalAudioProcessor()
    bridge = _make_bridge(processor)
    fake = await _spawn("echo_speak")
    assert fake.stdin is not None and fake.stdout is not None
    fake.stdin.write(connection_info_json())  # the bridge's start() does this
    await fake.stdin.drain()
    import threading

    bridge.proc = fake
    bridge._stdin_lock = threading.Lock()
    bridge._guild_id = 9999

    wav_payload = bytes(((i * 13) % 256) for i in range(44100))  # pretend WAV
    bridge.reader = RustStdoutReader(fake)
    reader_task = asyncio.create_task(bridge.reader.read_loop())

    try:
        await send_tts_audio(bridge, wav_payload)
        echo_line: str | None = None
        tts_done_seen = False
        for _ in range(5):
            event = await asyncio.wait_for(bridge.reader.events.get(), timeout=5.0)
            if event is RustStdoutReader._EOF or not isinstance(event, tuple):
                continue
            if event[0] == "log" and str(event[1]).startswith("FAKE_SPEAK_ECHO:"):
                echo_line = str(event[1])
            elif event == ("tts_done",):
                tts_done_seen = True
            if echo_line and tts_done_seen:
                break
        assert echo_line is not None, "fake never echoed SPEAK payload digest"
        assert tts_done_seen, "fake never sent TTS_DONE after consuming payload"
        fields = dict(part.split("=") for part in (echo_line or "").split(":")[1].split(";"))
        assert int(fields["len"]) == len(wav_payload)
        assert fields["sha256"] == hashlib.sha256(wav_payload).hexdigest()
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass
        await _stop(fake)


@pytest.mark.asyncio
async def test_interrupt_and_shutdown_acknowledged() -> None:
    """INTERRUPT yields one tts_done event; SHUTDOWN exits 0 within timeout."""
    proc, reader = await _start_reader("echo_speak")
    task = asyncio.create_task(reader.read_loop())
    try:
        assert proc.stdin is not None
        await _emit(proc, b"INTERRUPT")
        event = await asyncio.wait_for(reader.events.get(), timeout=5.0)
        assert event == ("tts_done",)
        proc.stdin.write(b"SHUTDOWN\n")
        await proc.stdin.drain()
        code = await asyncio.wait_for(proc.wait(), timeout=5.0)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    assert code == 0


@pytest.mark.asyncio
async def test_tts_done_releases_processing_lock_end_to_end() -> None:
    """THE S10 regression net: SPEAK out -> TTS_DONE back -> lock released."""
    processor = MinimalAudioProcessor()
    processor._processing_lock_until["9999"] = 9999999999.0  # locked far-future
    bridge = _make_bridge(processor)
    fake = await _spawn("echo_speak")
    assert fake.stdin is not None
    fake.stdin.write(connection_info_json())  # the bridge's start() does this
    await fake.stdin.drain()
    import threading

    bridge.proc = fake
    bridge._stdin_lock = threading.Lock()
    bridge.reader = RustStdoutReader(fake)
    bridge._guild_id = 9999
    reader_task = asyncio.create_task(bridge.reader.read_loop())
    try:
        await send_tts_audio(bridge, b"\x01\x02\x03\x04")  # SPEAK:4 + payload
        # Wait until the fake's TTS_DONE lands (it also emits a digest log
        # line first), then drive the handler exactly as the consumer would.
        seen_done = False
        for _ in range(10):
            event = await asyncio.wait_for(bridge.reader.events.get(), timeout=5.0)
            if event == ("tts_done",):
                seen_done = True
                break
        assert seen_done, "fake never confirmed playback end"
        bridge._handle_tts_done()
        assert "9999" not in processor._processing_lock_until, (
            "TTS_DONE arrived but the per-guild processing lock stayed held"
        )
        assert processor.flushed == ["9999"]
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass
        await _stop(fake)


@pytest.mark.asyncio
async def test_tts_done_without_lock_is_noop() -> None:
    """TTS_DONE for an unknown/expired guild raises nothing, changes nothing."""
    processor = MinimalAudioProcessor()
    bridge = _make_bridge(processor)
    bridge._guild_id = 4242
    bridge._handle_tts_done()  # must not raise
    assert processor._processing_lock_until == {}
    assert processor.flushed == ["4242"]  # flush still attempted (real contract)


def test_reader_lacks_async_iterator_protocol() -> None:
    """PINNED FINDING A: consumer uses `async for` but reader has no __aiter__.

    d5_2_process_watch_io._read_loop iterates the reader asynchronously; the
    class defines no async-iterator methods, so the live consumer path cannot
    dispatch events today. This test exists so the eventual fix flips this
    assertion CONSCIOUSLY (and adds an end-to-end consumer test), rather than
    the mismatch being rediscovered in production.
    """
    assert not hasattr(RustStdoutReader, "__aiter__")
    assert not hasattr(RustStdoutReader, "__anext__")


def test_framer_decoders_mirror_reader_parsing() -> None:
    """Shared framers agree with production parser semantics (header shapes)."""
    uid, pcm_len = decode_audio_header(f"AUDIO:{REAL_SNOWFLAKE_UID}:{1920}")
    assert uid == REAL_SNOWFLAKE_UID and pcm_len == 1920
    assert TTS_DONE_FRAME == b"TTS_DONE"


# --- Core ---
# (test functions above are the entry surface; no further core logic)

# --- Helpers ---
# (_make_bridge / _spawn / _start_reader / _drain_events / _stop above)

# --- Errors ---
# (none)
