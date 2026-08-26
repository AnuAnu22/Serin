"""Single source of truth for the Python<->Rust voice wire frame layouts.

Every test (and the fake receiver) encodes frames through this module so a
protocol change can never leave two disagreeing copies of a literal behind.
The literals below are pinned against ``voice/rust_receiver/src/main.rs`` by
``tests/integration/test_protocol_sync_guard.py`` — if you change them here,
update the fake and re-check main.rs in the same commit.

Protocol reference: voice/rust_receiver/src/main.rs module docstring and
docs/wiki/python-rust-voice-protocol.md.

Wire format (newline-delimited commands; raw binary payloads follow length
headers):
  stdout (Rust -> Python):
    AUDIO:{user_id}:{pcm_len}\n + pcm_len bytes   # decoded PCM
    JOIN:{user_id}\n / LEAVE:{user_id}\n          # speaking-set diff
    TTS_DONE\n                                    # TrackEvent::End fired
    anything else                                  # treated as a log line
  stdin (Python -> Rust):
    line 1: JSON ConnectionInfo + \n
    SPEAK:{byte_len}\n + byte_len bytes           # TTS WAV payload
    INTERRUPT\n / SHUTDOWN\n

# --- Imports ---
"""
from __future__ import annotations

import json
from typing import Any

# --- Constants ---

AUDIO_PREFIX = b"AUDIO:"
JOIN_PREFIX = b"JOIN:"
LEAVE_PREFIX = b"LEAVE:"
TTS_DONE_FRAME = b"TTS_DONE"
TTS_DONE_LINE = b"TTS_DONE\n"
SPEAK_PREFIX = b"SPEAK:"
INTERRUPT_FRAME = b"INTERRUPT\n"
SHUTDOWN_FRAME = b"SHUTDOWN\n"

NEWLINE = b"\n"

# A valid-looking ConnectionInfo. Discord snowflake ids are always >= 2**32
# (see io_bridge.py raw-SSRC guard); keep the defaults above that line.
DEFAULT_CONNECTION_INFO: dict[str, Any] = {
    "endpoint": "region-discord.media:443",
    "token": "fake-voice-token",
    "session_id": "fake-session-id",
    "guild_id": 845531416296361984,
    "channel_id": 845531416296361985,
    "user_id": 845531416296361986,
}

# --- Entry ---


def encode_audio(user_id: str, pcm: bytes) -> bytes:
    """Encode one AUDIO frame: header line + exactly ``len(pcm)`` raw bytes."""
    header = f"{AUDIO_PREFIX.decode()}{user_id}:{len(pcm)}\n".encode()
    return header + pcm


def encode_join(user_id: str) -> bytes:
    """Encode a JOIN frame."""
    return f"{JOIN_PREFIX.decode()}{user_id}\n".encode()


def encode_leave(user_id: str) -> bytes:
    """Encode a LEAVE frame."""
    return f"{LEAVE_PREFIX.decode()}{user_id}\n".encode()


def encode_speak(payload_len: int) -> bytes:
    """Encode a SPEAK header line (payload bytes follow separately)."""
    return f"{SPEAK_PREFIX.decode()}{payload_len}\n".encode()


def connection_info_json(info: dict[str, Any] | None = None) -> bytes:
    """Encode the stdin handshake: JSON ConnectionInfo followed by newline."""
    return (json.dumps(info if info is not None else DEFAULT_CONNECTION_INFO) + "\n").encode(
        "utf-8"
    )


def decode_speak(header_line: str) -> int:
    """Parse a SPEAK header line into its payload length.

    Raises:
        ValueError: if the line is not ``SPEAK:<int>``.
    """
    prefix = SPEAK_PREFIX.decode()
    if not header_line.startswith(prefix):
        raise ValueError(f"not a SPEAK header: {header_line!r}")
    return int(header_line[len(prefix):])


def decode_audio_header(header_line: str) -> tuple[str, int]:
    """Parse an AUDIO header line into ``(user_id, pcm_len)``.

    Raises:
        ValueError: if malformed or the length is not an integer.
    """
    prefix = AUDIO_PREFIX.decode()
    if not header_line.startswith(prefix):
        raise ValueError(f"not an AUDIO header: {header_line!r}")
    parts = header_line[len(prefix):].split(":")
    if len(parts) < 2:
        raise ValueError(f"AUDIO header missing fields: {header_line!r}")
    user_id = parts[0]
    pcm_len = int(parts[1])
    return user_id, pcm_len


# --- Helpers ---
# (none)

# --- Errors ---
# (none)
