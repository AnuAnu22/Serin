"""Fake voice_receiver — a test stand-in for the Rust voice subprocess.

Speaks the exact wire protocol documented in
voice/rust_receiver/src/main.rs (framers: tests/integration/protocol_framers.py)
without any Discord/DAVE/songbird dependency, so the real Python-side bridge
code can be executed end-to-end in CI.

Usage (spawned by tests via asyncio.create_subprocess_exec):
    <python> fake_voice_receiver.py --scenario join_then_audio \
        --pcm-bytes 1920 --chunks 3

Handshake:
    Line 1 on stdin MUST be valid ConnectionInfo JSON. On invalid JSON the
    fake prints FAKE_ERROR:bad_connection_info and exits 3 — loud failure,
    per docs/wiki/voice-debugging-log.md ("silent drops are the enemy").

Behavior is data-driven:
    --scenario join_then_audio   JOIN + N AUDIO frames up front
    --scenario echo_speak        SPEAK payloads consumed; TTS_DONE after each
    --scenario silent            handshake then wait for commands

Commands understood while running:
    EMIT:<frame-name>  emit a Rust->Python protocol frame (join|leave|
                       tts_done|audio) — the test bench for reader parsing
    RAW:<hex>          write <hex>-decoded bytes VERBATIM to stdout — lets
                       tests inject arbitrary/malformed wire content
                       (corruption simulation)
    INTERRUPT          emit one TTS_DONE (mirrors interrupt->track-stop->End)
    SPEAK:{len}+bytes  consume payload; TTS_DONE after it (echo_speak scenario)
    SHUTDOWN           clean exit 0. Stdin EOF also exits cleanly.

# --- Imports ---
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from protocol_framers import (  # noqa: E402
    TTS_DONE_LINE,
    decode_speak,
    encode_audio,
    encode_join,
    encode_leave,
)


def _out(data: bytes) -> None:
    """Write + flush immediately: partial-buffer delivery must stay correct."""
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _make_pcm(num_bytes: int, seed: int) -> bytes:
    """Deterministic pseudo-audio payload (no RNG semantics asserted)."""
    return bytes(((i * 31 + seed * 7) % 256) for i in range(num_bytes))


# --- Entry ---


def main() -> int:
    """Run the fake receiver against stdin/stdout."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="silent",
                        choices=["silent", "join_then_audio", "echo_speak"])
    parser.add_argument("--pcm-bytes", type=int, default=1920)
    parser.add_argument("--chunks", type=int, default=3)
    parser.add_argument("--user-id", default="845531416296361987")
    args = parser.parse_args()

    # --- Handshake: first stdin line must be ConnectionInfo JSON ---
    first = sys.stdin.buffer.readline()
    try:
        parsed = json.loads(first.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _out(b"FAKE_ERROR:bad_connection_info\n")
        return 3
    for key in ("endpoint", "token", "session_id"):
        if key not in parsed:
            _out(b"FAKE_ERROR:bad_connection_info\n")
            return 3

    if args.scenario == "join_then_audio":
        _out(encode_join(args.user_id))
        for idx in range(args.chunks):
            _out(encode_audio(args.user_id, _make_pcm(args.pcm_bytes, idx)))
    elif args.scenario != "echo_speak":
        _out(b"FAKE_READY\n")

    # --- Command loop ---
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return 0  # stdin EOF -> clean exit
        stripped = line.strip()
        if stripped == b"SHUTDOWN":
            return 0
        if stripped == b"EMIT:join":
            _out(encode_join(args.user_id))
            continue
        if stripped == b"EMIT:leave":
            _out(encode_leave(args.user_id))
            continue
        if stripped == b"EMIT:tts_done":
            _out(TTS_DONE_LINE)
            continue
        if stripped == b"EMIT:audio":
            _out(encode_audio(args.user_id, _make_pcm(args.pcm_bytes, 99)))
            continue
        if stripped.startswith(b"RAW:"):
            payload = bytes.fromhex(stripped[len(b"RAW:"):].decode("ascii"))
            # Terminate unless the test explicitly injects an unterminated
            # fragment (payload ending with \\n stays verbatim).
            _out(payload if payload.endswith(b"\n") else payload + b"\n")
            continue
        if stripped == b"INTERRUPT":
            _out(TTS_DONE_LINE)
            continue
        if stripped.startswith(b"SPEAK:"):
            header_len = decode_speak(stripped.decode("utf-8", errors="replace"))
            payload = sys.stdin.buffer.read(header_len)
            while len(payload) < header_len:
                more = sys.stdin.buffer.read(header_len - len(payload))
                if not more:
                    break
                payload += more
            if args.scenario == "echo_speak":
                digest = hashlib.sha256(payload).hexdigest()
                _out(f"FAKE_SPEAK_ECHO:len={len(payload)};sha256={digest}\n".encode())
                _out(TTS_DONE_LINE)
    # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
