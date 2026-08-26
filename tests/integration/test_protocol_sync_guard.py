"""Anti-drift sync guard: fake receiver + framers stay pinned to main.rs.

The fake binary is a stand-in, not a parallel truth. If the real protocol in
voice/rust_receiver/src/main.rs ever changes, this test fails AT THE SAME
COMMIT and forces the fake/framers to be updated together (or the change to
be consciously rejected). Drift becomes a red CI, not a silent production
break — see docs/wiki/dave-support-vs-receive-support.md ("silent drops are
the enemy").

# --- Imports ---
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.protocol_framers import (
    AUDIO_PREFIX,
    INTERRUPT_FRAME,
    JOIN_PREFIX,
    LEAVE_PREFIX,
    SHUTDOWN_FRAME,
    SPEAK_PREFIX,
    TTS_DONE_FRAME,
)

REPO_ROOT = Path(__file__).parents[2]
MAIN_RS = REPO_ROOT / "voice" / "rust_receiver" / "src" / "main.rs"
FAKE_PY = Path(__file__).parent / "fake_voice_receiver.py"

# Every wire literal the Python side knows about. If main.rs renames or adds
# frames, extend BOTH this list and protocol_framers.py.
REQUIRED_LITERALS: list[bytes] = [
    AUDIO_PREFIX,
    JOIN_PREFIX,
    LEAVE_PREFIX,
    TTS_DONE_FRAME,
    SPEAK_PREFIX,
    INTERRUPT_FRAME.strip(),
    SHUTDOWN_FRAME.strip(),
]


# --- Entry ---


@pytest.mark.skipif(not MAIN_RS.exists(), reason="voice/rust_receiver not present in checkout")
def test_framer_literals_exist_in_main_rs() -> None:
    """Every framer literal appears verbatim in the canonical Rust source."""
    rust_src = MAIN_RS.read_text(encoding="utf-8", errors="replace")
    missing = [lit.decode() for lit in REQUIRED_LITERALS if lit not in rust_src.encode()]
    assert not missing, (
        f"Literals {missing} no longer appear in voice/rust_receiver/src/main.rs. "
        "The wire protocol changed: update protocol_framers.py AND "
        "fake_voice_receiver.py in the SAME commit, then update this list."
    )


@pytest.mark.skipif(not FAKE_PY.exists(), reason="fake_voice_receiver.py missing")
def test_framer_literals_used_by_fake_receiver() -> None:
    """The fake speaks via the shared framers, not private copies of literals.

    ``connection_info_json`` is deliberately absent from the required list:
    the fake is the *consumer* of the handshake (it validates the JSON
    strictly and exits 3 on garbage); the producer of encoded handshakes is
    the test suite itself.
    """
    fake_src = FAKE_PY.read_text(encoding="utf-8")
    for name in (
        "TTS_DONE_LINE",
        "decode_speak",
        "encode_audio",
        "encode_join",
        "encode_leave",
    ):
        assert name in fake_src, (
            f"fake_voice_receiver.py no longer references {name!r} from "
            "protocol_framers.py — it may have grown its own frame literals."
        )
    # The only raw literals allowed in the fake are the bench commands
    # themselves (EMIT:/RAW:/SHUTDOWN) and doc mentions; never Rust->Python
    # frame CONSTRUCTION outside the framers.
    fake_bytes = FAKE_PY.read_bytes()
    assert b'f"AUDIO' not in fake_bytes and b'"AUDIO:" + ' not in fake_bytes, (
        "fake hardcodes AUDIO frame construction instead of protocol_framers"
    )


# --- Core ---
# (none)

# --- Helpers ---
# (none)

# --- Errors ---
# (none)
