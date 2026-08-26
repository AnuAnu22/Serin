"""Tier-B smoke: launch the REAL voice_receiver binary when it exists.

Catches "the binary doesn't even launch / spawn path rotted" — nothing more.
Full DAVE/UDP audio needs live Discord voice servers and is covered by the
manual release checklist, not CI.

Skips silently when the binary (or cargo) is absent so the default suite
stays green on machines without the Rust toolchain output.

# --- Imports ---
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

pytest.importorskip("pytest_asyncio")

from serin.d1_2_gateway_io.d2_4_io_di import init_gateway  # noqa: E402
from serin.d1_4_config_base.d2_3_core_logger import (
    logger as _default_logger,  # noqa: E402
)

init_gateway(_default_logger)

from tests.integration.protocol_framers import (  # noqa: E402
    DEFAULT_CONNECTION_INFO,
    SHUTDOWN_FRAME,
    connection_info_json,
)

REPO_ROOT = Path(__file__).parents[2]


def _candidate_binaries() -> list[Path]:
    """All plausible locations of a built voice_receiver binary."""
    return [
        REPO_ROOT / "voice" / "rust_receiver" / "target" / "release" / "voice_receiver",
        REPO_ROOT / "voice_receiver",
        REPO_ROOT / "voice" / "voice_receiver",
    ]


def _find_built_binary() -> Path | None:
    for candidate in _candidate_binaries():
        if candidate.is_file():
            return candidate
    return None


# --- Entry ---


def test_bridge_default_path_matches_real_binary_when_built() -> None:
    """If a binary exists on disk, the bridge's resolver must point at it.

    This is the spawn-path-rot tripwire: a moved binary with an unchanged
    resolver means production would silently fall back to no-voice. Uses a
    bare __new__ instance so no subprocess/Discord objects are touched.
    """
    built = _find_built_binary()
    if built is None:
        pytest.skip("no voice_receiver binary built — nothing to resolve")
    # Reproduce the constructor's default-path logic (d5_1_process_watch.py):
    # base = bridge file's dir + 4 parents up, then voice/rust_receiver/...
    watch_dir = (
        REPO_ROOT
        / "serin"
        / "d1_2_gateway_io"
        / "d2_2_voice_system"
        / "d3_2_bridge_io"
        / "d4_4_process_watch"
    )
    base = Path(os.path.abspath(os.path.join(str(watch_dir), *([os.pardir] * 4))))
    expected_default = base / "voice" / "rust_receiver" / "target" / "release" / "voice_receiver"
    assert built.resolve() == expected_default.resolve(), (
        f"binary lives at {built} but the bridge's default path resolves to "
        f"{expected_default} — update d5_1_process_watch.py default or move "
        "the binary; production would silently find nothing."
    )


@pytest.mark.asyncio
@pytest.mark.skipif(_find_built_binary() is None, reason="voice_receiver not built")
async def test_real_binary_handshake_and_shutdown() -> None:
    """Real binary: accepts ConnectionInfo line, exits cleanly on SHUTDOWN."""
    binary = _find_built_binary()
    assert binary is not None
    proc = await asyncio.create_subprocess_exec(
        str(binary),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write(connection_info_json(DEFAULT_CONNECTION_INFO))
        await proc.stdin.drain()
        # Give it a moment to either die on bad args or settle into its loop;
        # we cannot drive real Discord audio here — launch-only contract.
        await asyncio.sleep(0.5)
        alive = proc.returncode is None
        proc.stdin.write(SHUTDOWN_FRAME)
        await proc.stdin.drain()
        try:
            code = await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            proc.kill()
            pytest.fail(f"real binary ignored SHUTDOWN (alive={alive})")
        # Clean exit OR immediate arg rejection both prove launchability; a
        # hang or crash-on-launch is the failure this test exists for.
        assert code in (0,), f"real binary exited {code} after SHUTDOWN"
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


# --- Core ---
# (none)

# --- Helpers ---
# (_candidate_binaries / _find_built_binary above)

# --- Errors ---
# (none)
