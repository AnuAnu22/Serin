---
type: entity
tags: [voice, rust, bridge, subprocess]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/SUBSYSTEM_gateway_voice.md, docs/CONNECTIONS.md, docs/wiki/python-rust-voice-protocol.md]
status: seed
---

# RustVoiceBridge (Python ↔ Rust voice seam)

## What it is

The only production Python↔Rust voice seam. Spawns and supervises the Rust `voice_receiver`
binary; bridges PCM audio intake and TTS playback over a stdin/stdout line+binary protocol.
Rust owns ALL voice transport (UDP, DAVE, Opus, playback) — no second gateway client.

## Where it lives

- Class: `serin/d1_2_gateway_io/d2_2_voice_system/d3_2_bridge_io/d4_4_process_watch/d5_1_process_watch.py`
- Reader: `d4_1_io_bridge.py` (`RustStdoutReader`: async read loop, events queue, `_EOF`
  sentinel on pipe close)
- Audio intake: `AudioStreamProcessor` (delegating façade — state in class, logic lazy-imported
  from `audio_vad`/`audio_utils`/`audio_transcribe` siblings)

## Key behaviors

- **Spawn** (`RustVoiceBridge.start()`, ~:116-180): self-resolves the binary via `os.pardir`×4
  → `voice/rust_receiver/target/release/voice_receiver`; `asyncio.create_subprocess_exec`
  with `RUST_BACKTRACE=full`; first stdin line = `ConnectionInfo` JSON.
- **Wire protocol** — see [[voice_flow]] for the table; canonical docstring in
  `voice/rust_receiver/src/main.rs`. Logs go to stderr only (stdout is data).
- **Supervision**: 5-restarts/60s recovery (the old `d4_3_bridge_recovery.py` is DEAD — the
  live logic lives in process_watch).

## Notes / Known issues

- The 200-line stderr ring buffer + threading.Lock stdin serialization from the old design are
  superseded; `d4_3_bridge_recovery.py` has zero importers (see [[known_debt]]).
- **Testing gap**: `tests/integration/test_bridge.py` only exercises the missing-binary path;
  the wire framing (AUDIO/JOIN/LEAVE/TTS_DONE) is covered only by AST contract checks.
- Historical bug: the `_EOF` sentinel replaced the `queue.get(1.0)` timeout/EOF conflation
  that killed the healthy Rust process after 1s of silence (see [[dave_receive]]).

## See also

[[voice_flow]] · [[dave_receive]] · [[architecture]] · [[index]]
