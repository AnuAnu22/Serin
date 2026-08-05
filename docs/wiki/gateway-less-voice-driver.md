# Gateway-less voice: songbird Driver without a Discord gateway

**The core architectural trick of Serin's voice receive path: run songbird's
`Driver` as a standalone binary with *no* Discord gateway client, and feed it
connection credentials from Python's py-cord gateway over stdin.**

## The dual-gateway problem

Serin's main process is Python (py-cord), which already owns the one allowed
Discord gateway connection for the bot token. songbird normally rides on
serenity's or twilight's gateway to obtain voice credentials. Embedding a
second Rust gateway would mean two competing WebSocket sessions for the same
bot — session invalidation, event races, double identify.

## The solution

- Python performs the voice handshake itself: py-cord receives
  `VOICE_STATE_UPDATE` + `VOICE_SERVER_UPDATE`, yielding
  endpoint/token/session_id/guild_id/channel_id.
- Python spawns `voice_receiver` (Rust, `voice/rust_receiver/src/main.rs`) and
  writes that `ConnectionInfo` as one JSON line to its stdin.
- The Rust side builds a bare `songbird::Driver` — voice WebSocket + UDP only,
  no gateway. Cargo note: the `gateway` feature flag in
  `voice/rust_receiver/Cargo.toml` is enabled **only for shared deps**
  (dashmap, async-trait); no gateway client is constructed.
- The driver connects straight to Discord's voice servers, negotiates
  transport encryption and DAVE (see [[songbird-dave-offset-bug]]), decodes
  Opus → 48 kHz stereo i16 PCM, and streams it to Python via the stdout
  protocol ([[python-rust-voice-protocol]]).

## SSRC → user attribution

`Receiver` in `main.rs` keeps `known_ssrcs: DashMap<u32, u64>` (SSRC →
user_id), populated from `SpeakingStateUpdate` and — thanks to
[[songbird-clientconnect-patch]] — from `ClientConnect` at join time.
`VoiceTick` (one event per 20 ms, all speakers) then maps each speaking SSRC
to a user and emits `AUDIO:{user_id}:{len}` frames. Unknown SSRCs fall back to
the raw SSRC as the ID rather than dropping audio.

## Why this design won

- One gateway, one owner (Python) — no session conflicts.
- Rust handles the hard real-time work (UDP, Opus, DAVE decrypt, mixing/TTS
  playback); Python keeps the easy-to-iterate logic (VAD, whisper
  transcription, LLM, edge-tts).
- The receiver is crash-isolated: RustVoiceBridge
  (`serin/.../d4_4_process_watch/`) can respawn the process without touching
  the bot's gateway.

There is essentially no public prior art for songbird-as-receiver behind a
foreign gateway under DAVE; this file and the two patch articles are the
documentation.
