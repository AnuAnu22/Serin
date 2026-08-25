"""Songbird ClientConnect patch — presence contract.

The vendored songbird tree (``voice/rust_receiver/vendor/songbird``) carries the
ONE behavioral patch this project depends on: re-enabling the ``ClientConnect``
voice-gateway event for SSRC→user_id mapping. Upstream ignores ClientConnect as
"discontinued", but Discord still sends it — and without the mapping, the DAVE
decrypt path silently drops packets from unmapped SSRCs *before decryption*.

That patch dies silently on any re-vendor, vendor-folder deletion, or accidental
``[patch.crates-io]`` removal. These tests make its disappearance LOUD:
they fail at CI time instead of letting user audio vanish in production.

Provenance: ``docs/wiki/songbird-clientconnect-patch.md`` (patch = commit
``313a220``, 3 files, 18 lines) and ``docs/wiki/songbird-dave-offset-bug.md``
(the DAVE offset fix is already upstream in 0.6.0 — only ClientConnect is ours).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECEIVER_DIR = PROJECT_ROOT / "voice" / "rust_receiver"
VENDOR_SONGBIRD = RECEIVER_DIR / "vendor" / "songbird"

# The exact patch lines from commit 313a220 that must survive any re-vendor.
# Inside `GatewayEvent::ClientConnect(ev)` in ws.rs, both signalling maps must
# be populated BEFORE the core event fires — the receive-gated inserts are what
# feed ssrc_user_map, which udp_rx consults before DAVE-decrypting a packet.
_WS_RS_PATCH_MARKERS: tuple[str, ...] = (
    "GatewayEvent::ClientConnect(ev)",
    "self.ssrc_signalling.user_ssrc_map.insert(ev.user_id, ev.audio_ssrc)",
    "self.ssrc_signalling.ssrc_user_map.insert(ev.audio_ssrc, ev.user_id)",
)

_CORE_RS_PATCH_MARKERS: tuple[str, ...] = (
    "ClientConnect,",  # CoreEvent variant
)

_CONTEXT_RS_PATCH_MARKERS: tuple[str, ...] = (
    "ClientConnect(ClientConnect)",  # EventContext + CoreContext variants
)


def _read(relpath: str) -> str:
    path: Path = VENDOR_SONGBIRD / relpath
    assert path.exists(), (
        f"Vendored songbird file missing: {relpath}. "
        "The vendor tree must stay git-tracked and intact — see "
        "docs/wiki/songbird-clientconnect-patch.md."
    )
    return path.read_text(errors="replace")


def _assert_markers(source: str, markers: tuple[str, ...], where: str) -> None:
    for marker in markers:
        assert marker in source, (
            f"Songbird patch marker missing in {where}:\n  {marker!r}\n"
            "The ClientConnect SSRC-mapping patch (commit 313a220) appears to have "
            "been lost — likely by a re-vendor or dependency upgrade. Without it, "
            "audio from users who have not triggered a Speaking event yet is "
            "SILENTLY DROPPED before DAVE decryption.\n"
            "Re-apply the diff from docs/wiki/songbird-clientconnect-patch.md "
            "(commit 313a220), or update these markers if upstreaming removed "
            "the need for the patch."
        )


# ── Layer A: Cargo wiring — the [patch.crates-io] override ───────────────


def test_patch_section_points_songbird_at_vendor_tree() -> None:
    """Cargo.toml must override crates.io songbird with the vendored tree."""
    cargo_toml = RECEIVER_DIR / "Cargo.toml"
    assert cargo_toml.exists(), f"Missing {cargo_toml}"
    data = tomllib.loads(cargo_toml.read_text())
    patch = data.get("patch", {}).get("crates-io", {})
    songbird = patch.get("songbird")
    assert songbird is not None, (
        "[patch.crates-io] no longer overrides songbird — builds would silently "
        "resolve to unpatched crates.io songbird. Restore: "
        'songbird = { path = "vendor/songbird" }'
    )
    assert isinstance(songbird, dict), (
        "patch.crates-io.songbird should be an inline table"
    )
    vendor_rel: str | None = songbird.get("path")
    assert vendor_rel == "vendor/songbird", (
        f"[patch.crates-io] songbird path is {vendor_rel!r}, expected 'vendor/songbird'"
    )


def test_lockfile_resolves_songbird_to_the_patched_vendor_tree() -> None:
    """Cargo.lock's songbird entry must be a PATH dependency (no registry source).

    A path-patched dependency has NO ``source = "registry+..."`` line in
    Cargo.lock. If that line ever appears, the build resolved songbird from
    crates.io — i.e. the patch is NOT being applied — even if Cargo.toml still
    looks correct. This catches vendor-folder deletion with Cargo.toml text
    surviving, and stray `cargo update --precise` style escapes.
    """
    lock_text = (RECEIVER_DIR / "Cargo.lock").read_text(errors="replace")
    blocks = lock_text.split("[[package]]")
    songbird_blocks: list[str] = [
        block for block in blocks if block.lstrip().startswith('name = "songbird"')
    ]
    assert len(songbird_blocks) >= 1, "Cargo.lock has no songbird package block"
    for block in songbird_blocks:
        assert 'source = "registry' not in block, (
            "Cargo.lock resolves songbird from crates.io (registry source present) — "
            "the vendored patch tree is bypassed. Check [patch.crates-io] in "
            "voice/rust_receiver/Cargo.toml and regenerate the lockfile with the "
            "vendor tree present."
        )


# ── Layer B: the patched files themselves ────────────────────────────────


def test_ws_rs_still_populates_ssrc_maps_on_client_connect() -> None:
    _assert_markers(_read("src/driver/tasks/ws.rs"), _WS_RS_PATCH_MARKERS, "ws.rs")


def test_core_rs_still_declares_client_connect_event() -> None:
    _assert_markers(
        _read("src/events/core.rs"), _CORE_RS_PATCH_MARKERS, "events/core.rs"
    )


def test_context_rs_still_carries_client_connect_context() -> None:
    _assert_markers(
        _read("src/events/context/mod.rs"),
        _CONTEXT_RS_PATCH_MARKERS,
        "events/context/mod.rs",
    )


# ── Layer C: the consumer — voice_receiver must use the patch ────────────


def test_voice_receiver_handles_client_connect_event() -> None:
    main_rs = (RECEIVER_DIR / "src" / "main.rs").read_text(errors="replace")
    consumer_markers: tuple[str, ...] = (
        "Ctx::ClientConnect",
        "known_ssrcs",
    )
    _assert_markers(main_rs, consumer_markers, "voice/rust_receiver/src/main.rs")


def test_patch_documentation_link_survives() -> None:
    doc = PROJECT_ROOT / "docs" / "wiki" / "songbird-clientconnect-patch.md"
    assert doc.exists(), (
        "docs/wiki/songbird-clientconnect-patch.md is missing — it is the "
        "re-apply recipe for the patch and the tripwire's provenance."
    )
