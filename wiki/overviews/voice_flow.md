---
type: overview
tags: [voice, rust, flow]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/ARCHITECTURE.md, docs/CONNECTIONS.md, docs/wiki/python-rust-voice-protocol.md, docs/wiki/gateway-less-voice-driver.md]
status: seed
---

# Voice Flow (voice → response)

## The architectural bet

Rust owns ALL voice transport (UDP, voice websocket, DAVE decrypt, Opus decode, TTS playback)
as a standalone `voice_receiver` subprocess; Python (py-cord) owns the single Discord gateway
and does the "easy to iterate" logic (VAD, Whisper STT, LLM, edge-tts). Rationale: one gateway
connection per token — a second Rust gateway would conflict (see [[gateway_isolation]]).

## Join & connection

1. Gateway `on_voice_state_update` feeds `VoiceTracker`.
2. Python joins via py-cord `InfoCaptureProtocol` (captures endpoint/token/session_id —
   zero DAVE/UDP from Python).
3. `RustVoiceBridge.start()` self-resolves the binary
   (`voice/rust_receiver/target/release/voice_receiver`, `os.pardir`×4) and spawns it; first
   stdin line = `ConnectionInfo` JSON.
4. Rust builds a bare songbird `Driver` — no gateway client — connects straight to Discord
   voice servers, negotiates transport encryption + DAVE, decodes Opus → 48 kHz stereo i16 PCM.

## Wire protocol (newline-delimited; stdout is data, stderr is logs)

| Direction | Command | Meaning |
|---|---|---|
| Python→Rust | `SPEAK:{len}` + WAV | Play TTS |
| Python→Rust | `INTERRUPT` | Stop TTS |
| Python→Rust | `SHUTDOWN` | Clean exit |
| Rust→Python | `AUDIO:{uid}:{len}` + PCM | 20 ms of one user's audio (50 fps) |
| Rust→Python | `JOIN:{uid}` / `LEAVE:{uid}` | SSRC→uid speaking set diff |
| Rust→Python | `TTS_DONE` | Track ended → **releases the Python per-guild lock** |

## The TTS_DONE lock (load-bearing)

Python holds a per-guild processing lock while Serin speaks so the bot doesn't transcribe itself
or talk over its own TTS. `TTS_DONE` (from songbird `TrackEvent::End` via one-shot
`TtsDoneNotifier`) is the release signal — without it Python would guess playback duration
(guesses cut off TTS or made the bot deaf between turns).

## Receive attribution

SSRC→user_id map learned from `SpeakingStateUpdate` + `ClientConnect` (the vendored
[[dave_receive]] patch); unknown SSRCs fall back to raw SSRC rather than dropping audio.

## Python half

`AudioStreamProcessor` (delegating façade) buffers per-user PCM with VAD (RMS-150) under the
per-guild lock; `VoiceMemoryPipeline` transcribes (Whisper — 48k stereo → mono → 16k resample)
and routes to the response path; replies queue to `VoiceOutputManager`, TTS'd (edge-tts→ffmpeg
or Coqui), sent to Rust as `SPEAK:{len}`+WAV.

## See also

[[architecture]] · [[rust_voice_bridge]] · [[dave_receive]] · [[index]]
