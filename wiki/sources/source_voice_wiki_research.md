---
type: source
tags: [source, voice, dave, research]
created: 2026-08-26
updated: 2026-08-26
sources: [docs/wiki/gateway-less-voice-driver.md, docs/wiki/python-rust-voice-protocol.md]
verified: 2026-08-26
status: live
---

# Source: docs/wiki voice-research set

Provenance: `docs/wiki/gateway-less-voice-driver.md` + `docs/wiki/python-rust-voice-protocol.md`
(research notes distilled into the repo wiki during the Phase-1 voice work). Informs:
[[voice_flow]], [[rust_voice_bridge]], [[dave_receive]].

## Key contents

- Gateway-less driver rationale: keep py-cord's gateway, hand ConnectionInfo to a Rust
  songbird Driver → DAVE support without fighting two gateways.
- Wire protocol spec: stdin/stdout line-framed frames (`SPEAK:{len}`+WAV / `INTERRUPT` /
  `SHUTDOWN`; `AUDIO:{uid}:{len}`+PCM / `JOIN:{uid}` / `LEAVE:{uid}` / `TTS_DONE`),
  byte-pinned since Plan 4 by `test_protocol_sync_guard.py`.
- Phase-2 destination (Rust owns its own gateway shard) is specified in todo.md and now
  tracked as GitHub issue #39 with IPC expansion design (JOIN/LEAVE/TRANSCRIPT/CONNECTED).
- DAVE/E2EE constraints: transparent 128-byte header, SFM=1, ClientConnect SSRC mapping —
  see [[dave_receive]] for the vendored-patch saga and tripwires.

→ [[index]]
